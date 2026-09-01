"""Router de intents — fast path (docs/01).

Recibe texto (da igual si viene del menú, del campo escrito o, en el futuro,
de la voz) y lo resuelve contra el catálogo jarvis/intents.yaml:

1. Patrones con {slot} → regex con captura ("abre {app}" ← "abre chrome").
2. Patrones fijos → fuzzy matching con rapidfuzz (tolera tildes, mayúsculas
   y variaciones pequeñas de la frase).

Lo que no matchea queda para el slow path (LLM, fase 3): de momento se avisa.

Uso CLI: python -m jarvis.router "qué hora es"   → respuesta + latencia
"""

from __future__ import annotations

import importlib
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rapidfuzz import fuzz, process

INTENTS_PATH = Path(__file__).resolve().parent / "intents.yaml"

FUZZY_CUTOFF = 80  # score mínimo (0-100) para dar por bueno un patrón fijo


def _normalize(text: str) -> str:
    """minúsculas, sin tildes, sin signos, espacios colapsados."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Intent:
    id: str
    label: str
    category: str
    skill: str  # "modulo.funcion"
    patterns: tuple[str, ...]
    params: dict = field(default_factory=dict)

    @property
    def slot(self) -> str | None:
        """Nombre del {slot} del label, si lo hay (la UI lo pide al usuario)."""
        match = re.search(r"\{(\w+)\}", self.label)
        return match.group(1) if match else None


@dataclass(frozen=True)
class Result:
    text: str  # respuesta para mostrar/leer
    matched: bool  # False → candidato a slow path (LLM)
    intent_id: str | None
    elapsed_ms: float


class Router:
    def __init__(self, config: dict):
        self.config = config
        self.intents: list[Intent] = []
        self.categories: dict[str, str] = {}  # id categoría → label
        self._load_catalog()
        self._build_index()

    def _load_catalog(self) -> None:
        catalog = yaml.safe_load(INTENTS_PATH.read_text(encoding="utf-8"))
        for cat_id, cat in catalog["categories"].items():
            self.categories[cat_id] = cat["label"]
            for entry in cat["intents"]:
                self.intents.append(
                    Intent(
                        id=entry["id"],
                        label=entry["label"],
                        category=cat_id,
                        skill=entry["skill"],
                        patterns=tuple(entry["patterns"]),
                        params=entry.get("params", {}),
                    )
                )

    def _build_index(self) -> None:
        # Patrones con slot → lista de (regex, nombre_slot, intent).
        # Patrones fijos → lista paralela para rapidfuzz.
        self._slot_patterns: list[tuple[re.Pattern, str, Intent]] = []
        self._fixed_texts: list[str] = []
        self._fixed_intents: list[Intent] = []
        for intent in self.intents:
            for pattern in intent.patterns:
                slot_match = re.search(r"\{(\w+)\}", pattern)
                if slot_match:
                    # _normalize borraría las llaves: se protege el hueco con
                    # un centinela alfanumérico y luego se vuelve regex.
                    sentinel = "xslotx"
                    protected = pattern.replace(slot_match.group(0), sentinel)
                    regex = re.escape(_normalize(protected)).replace(
                        sentinel, r"(.+)"
                    )
                    self._slot_patterns.append(
                        (re.compile(f"^{regex}$"), slot_match.group(1), intent)
                    )
                else:
                    self._fixed_texts.append(_normalize(pattern))
                    self._fixed_intents.append(intent)
        # Más literal = más específico: "abre la carpeta {x}" antes que "abre {x}".
        self._slot_patterns.sort(key=lambda t: len(t[0].pattern), reverse=True)

    # -- API pública ---------------------------------------------------------

    def handle(self, text: str) -> Result:
        """Texto libre → intent (o aviso de que iría al slow path)."""
        start = time.perf_counter()
        normalized = _normalize(text)
        if not normalized:
            return Result("Dime algo.", False, None, _ms(start))

        # 1. Fuzzy sobre patrones fijos (más específicos que un slot genérico).
        best = process.extractOne(
            normalized,
            self._fixed_texts,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=FUZZY_CUTOFF,
        )
        if best:
            intent = self._fixed_intents[best[2]]
            return self._run(intent, {}, start)

        # 2. Regex de patrones con slot.
        for regex, slot_name, intent in self._slot_patterns:
            match = regex.match(normalized)
            if match:
                return self._run(intent, {slot_name: match.group(1)}, start)

        return Result(
            "Aún no sé hacer eso (irá al LLM en la fase 3).", False, None, _ms(start)
        )

    def run_intent(self, intent_id: str, slot_value: str | None = None) -> Result:
        """Dispatch directo desde el menú de la UI, sin matching."""
        start = time.perf_counter()
        intent = next(i for i in self.intents if i.id == intent_id)
        extra = {}
        if intent.slot and slot_value:
            extra[intent.slot] = slot_value
        return self._run(intent, extra, start)

    # -- interno -------------------------------------------------------------

    def _run(self, intent: Intent, extra: dict, start: float) -> Result:
        module_name, func_name = intent.skill.rsplit(".", 1)
        module = importlib.import_module(f"jarvis.skills.{module_name}")
        func = getattr(module, func_name)
        try:
            text = func(config=self.config, **intent.params, **extra)
        except Exception as exc:  # una skill rota no debe tumbar el asistente
            text = f"Error en la skill {intent.skill}: {exc}"
        return Result(text, True, intent.id, _ms(start))


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def main() -> None:
    from jarvis import config as config_module

    if len(sys.argv) < 2:
        print('Uso: python -m jarvis.router "qué hora es"')
        raise SystemExit(1)
    router = Router(config_module.load())
    result = router.handle(" ".join(sys.argv[1:]))
    print(f"[{result.elapsed_ms:.1f} ms] intent={result.intent_id} → {result.text}")


if __name__ == "__main__":
    main()
