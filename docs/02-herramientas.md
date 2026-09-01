# 02 — Herramientas y stack (todo gratuito)

Investigado en septiembre de 2026. Todas las opciones elegidas son gratuitas
para uso personal y corren en local.

## 1. Wake word (palabra de activación)

| Opción | Licencia | Notas |
|---|---|---|
| **openWakeWord** ✅ | Apache 2.0 (modelos preentrenados CC-BY-NC, OK para uso personal) | Corre en CPU con consumo mínimo; se puede entrenar una palabra propia ("Jarvis") con su pipeline de datos sintéticos |
| Porcupine (Picovoice) | Gratis con cuenta (límites) | Más fácil, pero requiere clave y cuenta — descartado por dependencia |

## 2. STT — voz a texto (español)

| Opción | Uso | Notas |
|---|---|---|
| **faster-whisper** ✅ | Transcripción principal | Whisper sobre CTranslate2; `small`/`medium` con int8 va fluido en CPU, y con GPU NVIDIA vuela. Excelente español |
| **Vosk (modelo es)** ✅ | Fast path opcional | Streaming real, ~50 MB, latencia bajísima; menos preciso — ideal para comandos cortos |
| whisper.cpp | Alternativa | Mismo modelo que faster-whisper; interesa si no usamos Python para el STT |

- **Silero VAD** (MIT): detección de voz para saber cuándo cortas de hablar — imprescindible para no esperar timeouts.

## 3. LLM local

| Opción | Notas |
|---|---|
| **Ollama** ✅ | Servidor local de LLMs, API OpenAI-compatible, gestiona modelos y GPU/CPU |
| **Qwen3 8B** ✅ | Apache 2.0, ~5 GB, function calling nativo en Ollama, buen español. El mejor equilibrio en 2026 para agentes locales |
| Qwen3 4B / Llama 3.2 3B | Plan B si el hardware va justo (respuestas más flojas pero rápidas) |
| LM Studio | Alternativa a Ollama con GUI (gratis, pero no open source) |

## 4. TTS — texto a voz (español)

| Opción | Notas |
|---|---|
| **Piper** ✅ (MIT) | El más rápido en CPU (~10× tiempo real en escritorio). Varias voces es_ES (`davefx`, `sharvard`, `carlfm`...). Streaming por frases |
| **Kokoro-82M** (Apache 2.0) | Más calidad, soporta español, sigue siendo ligero (corre incluso en CPU). Candidato a upgrade |
| Windows SAPI | Fallback de emergencia sin dependencias |

## 5. Herramientas SIN IA (deterministas, instantáneas)

| Necesidad | Herramienta | Notas |
|---|---|---|
| Buscar archivos | **Everything (voidtools)** + `es.exe` CLI | Índice NTFS instantáneo; gratis. La búsqueda de archivos por voz se vuelve inmediata |
| Tiempo/clima | **Open-Meteo** | API gratuita **sin clave** ni registro |
| Hora/fecha/timers | Python stdlib | — |
| Programar tareas/recordatorios | **APScheduler** (persistencia SQLite) + Windows Task Scheduler (`schtasks`) para lo que deba sobrevivir al proceso | — |
| Notificaciones | `winotify` / toasts nativos de Windows | — |
| Enviar correo | SMTP (`smtplib`) con contraseña de aplicación de Gmail/Outlook | Gratis; el secreto va en Credential Manager |
| Leer correo | IMAP (`imaplib`) | "¿Tengo correos nuevos?" |
| Abrir programas/carpetas | `os.startfile`, `subprocess`, accesos directos del menú inicio | Perfiles: "modo trabajo" abre N programas |
| Volumen | **pycaw** | Subir/bajar/mutear por voz |
| Ventanas | **pygetwindow** / `pywin32` | Minimizar todo, cambiar de app |
| Media (play/pausa/siguiente) | teclas multimedia vía `pyautogui`/`keyboard` | Controla Spotify, YouTube, etc. sin API |
| Portapapeles | `pyperclip` | "Lee lo que he copiado" |
| Capturas | `mss` | "Haz una captura" |
| Noticias | feeds RSS (`feedparser`) | Sin API keys |
| Audio I/O | `sounddevice` / `pyaudio` | Captura del micro en streaming |

## 6. Hardware — perfiles autodetectados

El asistente detecta los recursos al arrancar (VRAM vía `pynvml`/`nvidia-smi`,
RAM y núcleos vía `psutil`) y elige perfil solo; forzable en `config.yaml`.

| Perfil | Requisito | STT | LLM | Notas |
|---|---|---|---|---|
| **full** | GPU ≥10 GB VRAM (equipo objetivo: RTX 3080 Ti 12 GB) | faster-whisper `large-v3-turbo` o `medium` en GPU | Qwen3 8B en GPU (`keep_alive=-1`) | Experiencia completa; ~8-9 GB VRAM ocupados, queda margen |
| **gpu-lite** | GPU 6-8 GB | faster-whisper `small` en GPU | Qwen3 4B en GPU | — |
| **cpu** | Solo CPU, ≥16 GB RAM | whisper `small` int8 + Vosk para fast path | Qwen3 4B en CPU | Slow path más lento → más peso al feedback hablado |
| **minimal** | Portátil justo / VM de desarrollo | Solo Vosk | LLM desactivado (u opcional) | Solo fast path; el asistente avisa de qué no puede hacer |

Piper (TTS) corre en CPU en todos los perfiles: ya es ~10× tiempo real.

## Fuentes

- [Benchmarks STT open source 2026 (Northflank)](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [faster-whisper vs whisper.cpp 2026](https://codersera.com/blog/faster-whisper-vs-whisper-cpp-speech-to-text-2026/)
- [Mejores TTS locales 2026](https://localaimaster.com/blog/best-local-tts-models) · [Kokoro setup](https://localaimaster.com/blog/kokoro-tts-local-setup) · [Piper setup](https://localaimaster.com/blog/piper-tts-setup-guide)
- [Mejores modelos Ollama para agentes 2026](https://localaimaster.com/blog/best-ollama-models-for-agents) · [LLMs locales con function calling](https://insiderllm.com/guides/function-calling-local-llms/)
- [openWakeWord (GitHub)](https://github.com/dscripka/openWakeWord) · [Guía wake word 2026](https://picovoice.ai/blog/complete-guide-to-wake-word/)
