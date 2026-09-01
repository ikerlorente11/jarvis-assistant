# 05 — Roadmap por fases

**Cambio de plan (sept. 2026)**: sin micrófono disponible por ahora, la
interfaz inicial es la **bolita flotante** (menús + texto). La voz pasa a ser
la última capa: se enchufa al mismo router sin tocar el motor. La bolita no es
temporal — se queda siempre como ayuda de accesibilidad.

Cada fase termina con algo usable; no se avanza sin validar la anterior.

## Fase 0 — Entorno y repo (½ día)

- Repo git → GitHub **ikerlorente11/jarvis-assistant**.
- Python 3.11+ en Windows nativo, venv, `requirements.txt` con versiones fijadas.
- Instalar Ollama (`ollama pull qwen3:8b`) y Everything + `es.exe`.
- **Primer módulo real: gestor de perfiles de hardware** (VRAM/RAM/CPU →
  `full`/`gpu-lite`/`cpu`/`minimal`). Se escribe ya porque todo depende de él
  y permite desarrollar en cualquier máquina.
- **Salida**: `python -m jarvis.profile` imprime el perfil detectado.

## Fase 1 — Bolita + esqueleto del motor (3-4 días)

- Widget PySide6: bola sin marco, siempre encima, arrastrable, en la esquina.
- Panel al hacer click: menús por categorías **generados desde el catálogo de
  intents** + campo de texto libre.
- Router fast path (tabla YAML + rapidfuzz) con 3-4 skills de prueba
  (hora, abrir programa, abrir carpeta).
- **Criterio de salida**: click en "¿Qué hora es?" del menú → respuesta en
  pantalla <300 ms; lo mismo escrito en el campo de texto.

## Fase 2 — Fast path completo (3-5 días)

- Todas las skills [F] de docs/03: programas/carpetas/URLs, perfiles de apps,
  volumen, timers, tiempo (Open-Meteo), buscar archivos (Everything), notas,
  media keys, capturas, batería...
- TTS opcional (Piper): que la bolita pueda leer las respuestas en voz alta.
- **Criterio de salida**: 15-20 comandos diarios fiables desde el menú, sin LLM.

## Fase 3 — Cerebro LLM (3-5 días)

- Fallback al LLM vía Ollama con function calling: mismas skills como tools
  + respuesta conversacional, escribiendo en el campo de texto.
- Respuesta en streaming en el panel (y por TTS frase a frase si está activo).
- Contexto corto de conversación (últimas N interacciones).
- **Criterio de salida**: pregunta libre con primera palabra <2 s (perfil
  `full`); "ábreme eso que usé ayer para las fotos" resuelto por tools.

## Fase 4 — Skills con estado y comunicación (1 semana)

- Recordatorios y tareas programadas persistentes (APScheduler + SQLite,
  `schtasks` para lo crítico) + notificaciones toast.
- Correo: enviar (redacta LLM → lo revisas → confirmas) y leer nuevos.
- Dictado→portapapeles queda aplazado a la fase de voz; conversiones y RSS sí.
- **Criterio de salida**: un recordatorio sobrevive a un reinicio y avisa.

## Fase 5 — Voz (cuando haya micrófono) (3-5 días)

- openWakeWord + earcon, Silero VAD, faster-whisper → entregan texto al
  router ya existente. El motor no cambia.
- TTS en streaming como salida principal; "para" interrumpe.
- La bolita pasa a mostrar también el estado "escuchando" y la transcripción.
- **Criterio de salida**: wake→beep <200 ms; comando fast path por voz <1.5 s.

## Fase 6 — Pulido y arranque con Windows (continuo)

- Autoarranque (Programador de tareas), icono en bandeja, `install.ps1` completo.
- Entrenar wake word personalizada ("Jarvis") con openWakeWord.
- Revisión de métricas de latencia; ideas futuras de docs/03.

## Estimación

**2-3 semanas** hasta asistente diario útil por bolita (fases 0-4);
la voz (fase 5) se añade cuando haya micro sin rehacer nada.
