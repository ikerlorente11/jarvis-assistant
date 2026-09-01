# JARVIS Assistant — Asistente de escritorio por voz

Asistente de escritorio estilo JARVIS: le hablas por el micro y ejecuta tareas
(abrir programas, buscar archivos, programar tareas, enviar correos, responder
preguntas...). **100% gratuito y local**: sin servicios de pago ni dependencia
obligatoria de la nube.

## Principios de diseño

1. **Local-first**: todos los modelos de IA corren en tu máquina (STT, TTS, LLM).
2. **Rápido o con feedback**: nunca silencio. Sonido/voz de confirmación inmediata
   y respuesta en streaming mientras piensa.
3. **Dos velocidades**: comandos frecuentes por *fast path* (sin IA, <1 s);
   solo lo complejo pasa por el LLM.
4. **Gratuito**: licencias MIT/Apache y APIs gratuitas sin clave de pago.
5. **Adaptativo**: detecta el hardware al arrancar (GPU/VRAM/RAM) y elige
   perfil solo — corre igual en el equipo objetivo (RTX 3080 Ti 12 GB, perfil
   `full`) que en un portátil de desarrollo sin GPU (perfil `cpu`/`minimal`).

## Documentación

| Doc | Contenido |
|---|---|
| [01-arquitectura.md](docs/01-arquitectura.md) | Pipeline de voz, fast/slow path, procesos |
| [02-herramientas.md](docs/02-herramientas.md) | Stack completo: STT, TTS, LLM, wake word, APIs, licencias |
| [03-capacidades.md](docs/03-capacidades.md) | Catálogo de todas las habilidades del asistente |
| [04-rendimiento-feedback.md](docs/04-rendimiento-feedback.md) | Estrategias de latencia y feedback al usuario |
| [05-roadmap.md](docs/05-roadmap.md) | Fases de implementación, de MVP a completo |
| [06-decisiones-riesgos.md](docs/06-decisiones-riesgos.md) | Decisiones abiertas y riesgos conocidos |
| [07-despliegue.md](docs/07-despliegue.md) | Despliegue nativo (sin Docker), estructura del repo, install.ps1 |

## Estado actual

- Repo destino: **github.com/ikerlorente11/jarvis-assistant**
- Interfaz inicial: **bolita flotante** (PySide6) con menús por categorías y
  entrada de texto — permanente como ayuda de accesibilidad. La **voz se
  aplaza a la Fase 5** (sin micrófono disponible ahora); se enchufará al mismo
  router sin cambiar el motor.

## Stack resumido (detalles en docs/02)

- **Wake word**: openWakeWord (gratis, corre en CPU)
- **STT**: faster-whisper (preciso) + Vosk (comandos ultrarrápidos) — español
- **LLM**: Ollama + Qwen3 8B (function calling nativo, buen español)
- **TTS**: Piper (tiempo real en CPU, voces es_ES) — Kokoro como alternativa de calidad
- **Sin IA**: Everything (búsqueda de archivos instantánea), Open-Meteo (tiempo sin API key), APScheduler (tareas), SMTP (correo)
