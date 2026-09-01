"""Slow path: cliente de Ollama con function calling (docs/01).

Lo que el router no reconoce llega aquí. El catálogo de intents se expone
al LLM como tools — una sola implementación de cada acción, dos formas de
invocarla (menú/texto directo y LLM). La respuesta llega en streaming vía
callback para pintarla token a token.
"""

from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime

import requests

from jarvis.profile import Profile
from jarvis.router import Router

OLLAMA = "http://localhost:11434"
MAX_TOOL_ROUNDS = 4  # llamadas encadenadas de tools antes de cortar

SYSTEM_PROMPT = """Eres JARVIS, un asistente de escritorio que corre en local.
Responde SIEMPRE en español, breve y directo (1-3 frases), sin markdown.
Si la petición encaja con una de tus herramientas, úsala en vez de explicar
cómo hacerlo; tras usarla, cuenta SOLO lo que la herramienta devolvió, tal
cual: nunca afirmes que algo se envió o completó si el resultado no lo dice.
Hoy es {fecha}."""


def _sin_razonamiento(content: str) -> str:
    """Quita el bloque de razonamiento de los modelos 'pensadores' (qwen3
    thinker): todo lo anterior a </think> es pensamiento interno."""
    if "</think>" in content:
        content = content.split("</think>", 1)[1]
    return content.lstrip("\n")


class _ThinkFilter:
    """Streaming sin razonamiento: retiene tokens hasta saber si el modelo
    está pensando; si aparece </think>, lo anterior se descarta."""

    def __init__(self, emit, expect_think: bool):
        self._emit = emit
        self._buffer = ""
        self._passthrough = not expect_think  # instruct: directo, sin retener
        self._started = False  # ya se emitió algo no vacío

    def feed(self, token: str) -> None:
        if self._passthrough:
            if not self._started:
                token = token.lstrip("\n")
                if not token:
                    return
                self._started = True
            self._emit(token)
            return
        self._buffer += token
        if "</think>" in self._buffer:
            rest = _sin_razonamiento(self._buffer)
            self._buffer = ""
            self._passthrough = True
            if rest:
                self._started = True
                self._emit(rest)

    def flush(self) -> None:
        """Fin del stream sin </think>: no había razonamiento, se emite todo."""
        if not self._passthrough and self._buffer:
            self._emit(self._buffer)
            self._buffer = ""


class Brain:
    def __init__(self, config: dict, router: Router, profile: Profile):
        self.config = config
        self.router = router
        self.model = profile.llm_model
        # los qwen3 "thinker" emiten razonamiento; los -instruct no
        self.thinker = self.model is not None and "instruct" not in self.model
        self.enabled = profile.llm_enabled and self.model is not None
        self.history: deque[dict] = deque(maxlen=12)  # últimas 6 interacciones
        self._tools = self._build_tools()
        if self.enabled:
            # cargar el modelo en VRAM ya (keep_alive=-1): que la primera
            # pregunta real no pague los ~20 s de carga
            threading.Thread(target=self._warm, daemon=True).start()

    def _warm(self) -> None:
        try:
            requests.post(
                f"{OLLAMA}/api/chat",
                json={"model": self.model, "messages": [], "keep_alive": -1},
                timeout=(5, 300),
            )
        except requests.RequestException:
            pass  # sin Ollama, available() ya avisa al usar el LLM

    # -- API -----------------------------------------------------------------

    def available(self) -> str | None:
        """None si todo bien; si no, el motivo (para avisar al usuario)."""
        if not self.enabled:
            return "El LLM está desactivado en este perfil de hardware."
        try:
            requests.get(f"{OLLAMA}/api/version", timeout=2)
        except requests.RequestException:
            return "Ollama no está en marcha (arranca la app de Ollama)."
        return None

    def quick(self, instruccion: str, texto: str) -> str | None:
        """Petición simple sin tools ni historial (resumir un correo, una
        noticia...). None si el LLM no está disponible."""
        if not self.enabled or self.available() is not None:
            return None
        try:
            response = requests.post(
                f"{OLLAMA}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system",
                         "content": "Responde en español, breve y sin markdown."},
                        {"role": "user", "content": f"{instruccion}\n\n{texto}"},
                    ],
                    "stream": False,
                    "think": False,
                    "keep_alive": -1,
                },
                timeout=(5, 300),
            )
            response.raise_for_status()
            return _sin_razonamiento(
                response.json()["message"]["content"]
            ).strip() or None
        except (requests.RequestException, KeyError, ValueError):
            return None

    def chat(self, text: str, on_token=None) -> str:
        """Conversa con tools; on_token(str) recibe la respuesta en streaming."""
        emit = on_token or (lambda token: None)
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    fecha=f"{datetime.now():%A %d/%m/%Y, %H:%M}"
                ),
            },
            *self.history,
            {"role": "user", "content": text},
        ]

        content = ""
        for _ in range(MAX_TOOL_ROUNDS):
            content, tool_calls = self._request(messages, emit)
            if not tool_calls:
                break
            messages.append(
                {"role": "assistant", "content": content, "tool_calls": tool_calls}
            )
            for call in tool_calls:
                messages.append(
                    {"role": "tool", "content": self._run_tool(call)}
                )

        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": content})
        return content

    # -- interno -------------------------------------------------------------

    def _request(self, messages: list[dict], emit) -> tuple[str, list]:
        response = requests.post(
            f"{OLLAMA}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "tools": self._tools,
                "stream": True,
                "think": False,  # sin razonamiento: latencia primero
                "keep_alive": -1,  # el modelo se queda en memoria
            },
            stream=True,
            timeout=(5, 300),
        )
        response.raise_for_status()
        filtro = _ThinkFilter(emit, expect_think=self.thinker)
        content = ""
        tool_calls: list = []
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            message = chunk.get("message", {})
            if message.get("tool_calls"):
                tool_calls.extend(message["tool_calls"])
            token = message.get("content", "")
            if token:
                content += token
                filtro.feed(token)
            if chunk.get("done"):
                break
        filtro.flush()
        return _sin_razonamiento(content), tool_calls

    def _run_tool(self, call: dict) -> str:
        name = call.get("function", {}).get("name", "")
        args = call.get("function", {}).get("arguments") or {}
        intent = next((i for i in self.router.intents if i.id == name), None)
        if intent is None:
            return f"Error: no existe la herramienta {name}."
        slot_value = None
        if intent.slot:
            slot_value = str(args.get(intent.slot, "")).strip() or None
            if slot_value is None:
                return f"Error: falta el argumento {intent.slot}."
        result = self.router.run_intent(intent.id, slot_value)
        text = result.text
        if any(i.kind == "intent" for i in result.items):
            # botones de confirmación humana (enviar un correo, etc.)
            text += ("\nIMPORTANTE: esto es SOLO un borrador, NO se ha enviado. "
                     "El usuario debe revisarlo y pulsar el botón de confirmar. "
                     "Dile exactamente eso.")
        elif result.items:
            text += " " + "; ".join(i.label for i in result.items[:8])
        return text

    def _build_tools(self) -> list[dict]:
        """Un tool por intent del catálogo; el {slot} es su único parámetro."""
        tools = []
        for intent in self.router.intents:
            if intent.no_tool:  # confirmaciones humanas: fuera del LLM
                continue
            properties, required = {}, []
            if intent.slot:
                properties[intent.slot] = {
                    "type": "string",
                    "description": f"{intent.slot} ({intent.label})",
                }
                required.append(intent.slot)
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": intent.id,
                        "description": intent.description or intent.label,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    },
                }
            )
        return tools
