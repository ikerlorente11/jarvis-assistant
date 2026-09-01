# 01 — Arquitectura

## Entorno de ejecución (importante)

El desarrollo se hace en WSL2, pero **el asistente debe ejecutarse en Windows
nativo** (Python para Windows):

- WSL2 no tiene acceso directo al micrófono ni a los altavoces.
- Abrir programas, carpetas, controlar volumen, notificaciones, etc. son
  acciones del escritorio de Windows.
- Ollama y Everything se instalan como servicios de Windows; el asistente les
  habla por HTTP/CLI en localhost.

Lenguaje: **Python 3.11+** (ecosistema de audio/IA maduro; suficiente porque el
trabajo pesado lo hacen los modelos en C++/ONNX).

## Capas de entrada (la voz es un adaptador más)

El motor (router + skills + LLM) recibe **texto** y no sabe de dónde viene.
Las entradas son adaptadores intercambiables:

1. **Bolita flotante (PySide6)** — *la primera que se construye; permanente
   como ayuda de accesibilidad*:
   - Widget circular sin marco, siempre visible en una esquina, arrastrable.
   - Click → panel con **menús por categorías** (Programas, Archivos, Tareas,
     Sistema, Información...) generados automáticamente desde el catálogo de
     intents — así cada skill nueva aparece sola en el menú y se puede testear
     todo sin voz.
   - Campo de texto libre para órdenes escritas (ejercita exactamente el mismo
     router que usará la voz).
   - La bolita muestra el estado con color/animación: reposo / trabajando /
     hablando. Cuando llegue la voz, también "escuchando".
2. **Voz** (fase posterior, cuando haya micrófono): wake word + VAD + STT
   producen texto y lo entregan al mismo router. Nada del motor cambia.

La salida hablada (TTS Piper) es independiente del modo de entrada: activable
desde el principio aunque se use la bolita (config `tts.enabled`).

## Pipeline de voz (fase posterior)

```
Micro (stream continuo)
  └─► [1] Wake word (openWakeWord, siempre escuchando, ~1% CPU)
        └─► ♪ earcon inmediato (<200 ms) + UI "escuchando"
  └─► [2] VAD (Silero VAD): detecta cuándo empiezas y terminas de hablar
  └─► [3] STT (faster-whisper small/medium, es): audio → texto
  └─► [4] ROUTER DE INTENTS  ◄── el corazón del diseño
        ├─► FAST PATH: regex/fuzzy match de comandos conocidos
        │     "abre chrome", "qué hora es", "sube el volumen"
        │     → ejecuta directamente, SIN LLM  →  respuesta total <1.5 s
        └─► SLOW PATH: todo lo demás → LLM local (Ollama + Qwen3 8B)
              ├─► con function calling: el LLM elige una herramienta
              │     (buscar archivo, crear recordatorio, enviar correo...)
              └─► o respuesta conversacional (preguntas generales)
              → feedback hablado inmediato ("voy a ello") + streaming
  └─► [5] TTS (Piper): texto → voz, frase a frase (no espera al texto completo)
  └─► [6] Ejecutor de acciones (subprocess, APIs de Windows, HTTP)
```

## Procesos

- **Gestor de perfiles de hardware** (primer paso del arranque): detecta
  VRAM/RAM/CPU (`pynvml` + `psutil`) y fija qué modelos se cargan y dónde
  (perfiles `full`/`gpu-lite`/`cpu`/`minimal`, ver docs/02 §6). El resto del
  código es agnóstico: pide "el STT" o "el LLM" y recibe el que toque, o un
  aviso claro de capacidad desactivada.
- **Daemon principal** (arranca con Windows): mantiene cargados en RAM el wake
  word, VAD, STT y la conexión a Ollama. Nada de cargar modelos por petición —
  ahí muere la latencia.
- **Ollama** como servicio aparte (ya funciona así): modelo con
  `keep_alive=-1` para que Qwen3 no se descargue de memoria.
- **Workers**: acciones lentas (búsquedas, correo, LLM) corren en hilos/async
  para no bloquear la escucha; puedes interrumpir con la wake word.
- **UI ligera** (opcional, fase tardía): overlay/system tray con estado
  (idle / escuchando / pensando / hablando) y transcripción en vivo.

## Router de intents (fast path)

- Tabla de intents en YAML/JSON: patrones (regex + sinónimos) → acción + parámetros.
- Matching con `rapidfuzz` para tolerar variaciones ("ábreme el chrome").
- Cubre el ~80% del uso diario (ver docs/03); el LLM es el fallback, no la puerta de entrada.
- El mismo catálogo de acciones se expone al LLM como *tools* (function calling):
  una sola implementación de cada acción, dos formas de invocarla.

## Configuración

- `config.yaml`: nombre de activación, voz, rutas de programas, alias
  ("el navegador" → chrome), cuenta SMTP, ciudad para el tiempo.
- Secretos (contraseña de aplicación de Gmail) en variables de entorno o
  Windows Credential Manager, nunca hardcodeados.
