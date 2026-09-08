# 07 — Despliegue y estructura del repo

## Decisión: nativo en Windows, sin Docker

El asistente necesita micrófono/altavoces, abrir programas, controlar volumen
y ventanas, y GPU con latencia mínima — todo lo que un contenedor aísla.
Docker no aporta nada aquí y añade capas de fallo. La reproducibilidad se
consigue con `install.ps1` + versiones fijadas en `requirements.txt`.

## Piezas (todas nativas)

| Pieza | Cómo se instala | Cómo hablamos con ella |
|---|---|---|
| **Ollama** | Instalador oficial Windows (winget) — servicio con GPU directa | HTTP `localhost:11434` |
| **Everything** | Instalador oficial + `es.exe` | CLI |
| **Asistente** | Este repo + venv Python 3.11+ | — |
| Modelos | `ollama pull qwen3:8b`, voz Piper es_ES, openWakeWord, Vosk | Ficheros en `models/` |

## Repositorio

- **GitHub: `ikerlorente11/jarvis-assistant`** (público, licencia PolyForm Noncommercial).
- `models/` y secretos **fuera del repo** (`.gitignore`); los descarga
  `install.ps1`. Secretos (SMTP) en Windows Credential Manager.

```
jarvis-assistant/
├── README.md
├── docs/                  # esta planificación
├── config.yaml            # alias, voz, ciudad, perfil hardware, tts.enabled
├── requirements.txt       # versiones fijadas
├── install.ps1            # instalación reproducible (ver abajo)
├── models/                # (gitignored) voces Piper, openWakeWord, Vosk
└── jarvis/
    ├── __main__.py        # python -m jarvis [--debug] [--profile X]
    ├── profile.py         # detector de hardware → perfil
    ├── router.py          # fast path: tabla de intents + rapidfuzz
    ├── brain.py           # slow path: cliente Ollama + function calling
    ├── intents.yaml       # catálogo de intents (alimenta router Y menús UI)
    ├── skills/            # una acción por módulo: apps, archivos, correo...
    ├── ui/                # bolita flotante PySide6 + panel de menús
    └── audio/             # (fase 5) micro, wake word, VAD, STT, TTS
```

Un solo proceso Python con asyncio/hilos. Sin microservicios ni colas.

## UI: PySide6

- **PySide6** (LGPL, gratis): ventana sin marco, siempre encima, transparente,
  arrastrable — todo soportado de serie; icono en bandeja incluido.
- Los menús del panel se generan leyendo `intents.yaml`: skill nueva →
  aparece en el menú sin tocar la UI.

## install.ps1 (qué hace)

1. Comprueba/instala Python 3.11, Ollama y Everything vía `winget`.
2. Crea venv + `pip install -r requirements.txt`.
3. Descarga modelos según el perfil detectado (`ollama pull`, voz Piper...).
4. (Opcional, fase 6) Registra autoarranque en el Programador de tareas.

Instalar en otra máquina = `git clone` + `.\install.ps1`.

## Desarrollo y actualización

- Desarrollo: `python -m jarvis --debug` (consola con métricas de latencia);
  `--profile minimal` para simular una máquina floja.
- Actualizar producción: `git pull` + reiniciar daemon.
- Empaquetado PyInstaller: solo si algún día se quiere distribuir.
