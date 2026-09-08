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

## Estado actual (sept. 2026)

**Fases 0-5 completadas** + gran parte de la 6: el asistente ya se maneja
**por voz** («Hey Jarvis» + comando) además de por bolita/teclado. Queda de
la fase 6 la wake word personalizada («Jarvis» a secas) y pulido continuo.

Lo que ya funciona:

- **Voz (fase 5)**: openWakeWord («Hey Jarvis») siempre escuchando con
  consumo mínimo → earcon inmediato + bolita en violeta → Silero VAD detecta
  el final del comando → faster-whisper (GPU según perfil) → el mismo router
  de siempre. Decir «Hey Jarvis» corta al TTS (barge-in) y «para» lo calla.
  El micrófono se elige por preferencia configurable (webcam → Momentum 4 →
  Barracuda X) con selector en Ajustes; un bluetooth apagado se salta solo.
- **Panel lanzador** estilo Spotlight (bolita flotante opcional + atajo global
  `Ctrl+Alt+J` + icono en bandeja), temas claro/oscuro/sistema, sugerencias en
  vivo al escribir, resultados clicables con iconos, mando multimedia con
  volumen del sistema en vivo.
- **Fast path**: ~40 acciones (programas por aproximación, carpetas y archivos
  vía Everything, tiempo con tarjetas estilo Google y geolocalización real de
  Windows, volumen, capturas, timers, notas, noticias RSS, conversor…).
- **Cerebro LLM** (Ollama + Qwen3 con function calling): el catálogo entero
  como tools, streaming, contexto de conversación.
- **Recordatorios persistentes** (APScheduler + SQLite): sobreviven a reinicios.
- **Correo completo**: enlazado por Ajustes (credenciales en el Almacén de
  Windows), leer no leídos / por remitente / último con resumen del LLM, y
  envío con borrador + confirmación humana, HTML con estilos, adjuntos e
  imágenes incrustadas.
- **Personalización por comandos**: alias, contactos y modos multi-orden
  ("crea el modo cine con netflix.com en la pantalla secundaria y baja el
  volumen") con colocación de ventanas por monitor.
- **TTS opcional** (Piper + Kokoro, 7 voces, normalización de dicción) con
  precarga y volumen propio.
- Arranque automático con Windows y `install.ps1` reproducible.

## Stack resumido (detalles en docs/02)

- **Wake word**: openWakeWord (gratis, corre en CPU)
- **STT**: faster-whisper (preciso) + Vosk (comandos ultrarrápidos) — español
- **LLM**: Ollama + Qwen3 8B (function calling nativo, buen español)
- **TTS**: Piper (tiempo real en CPU, voces es_ES) — Kokoro como alternativa de calidad
- **Sin IA**: Everything (búsqueda de archivos instantánea), Open-Meteo (tiempo sin API key), APScheduler (tareas), SMTP (correo)

## Licencia

Puedes usar, modificar y compartir este proyecto libremente para fines **no comerciales**.
No está permitido venderlo ni ganar dinero con él. Ver [LICENSE](LICENSE) (PolyForm Noncommercial 1.0.0).
