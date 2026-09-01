# 04 — Rendimiento y feedback

Objetivo: que **nunca** parezca colgado. Dos armas: latencia baja donde se
puede, y feedback continuo donde no.

## Presupuesto de latencia (objetivos)

| Momento | Objetivo | Cómo |
|---|---|---|
| Wake word → earcon | < 200 ms | openWakeWord en streaming + sonido pregrabado |
| Fin de frase detectado | < 300 ms tras callar | Silero VAD (no timeouts fijos) |
| Comando fast path completo | < 1.5 s total | Sin LLM; acción + respuesta TTS cacheada |
| Primera palabra hablada del LLM | < 2 s | Streaming de tokens → TTS frase a frase |
| Interrupción ("para") | < 300 ms | El wake word sigue activo mientras habla |

## Reglas de oro anti-cuelgue

1. **Modelos siempre en RAM**: daemon residente; Ollama con `keep_alive=-1`.
   Cargar Whisper por petición = 5-10 s muertos, prohibido.
2. **Feedback inmediato en 3 capas**:
   - *Earcon* (beep corto) al detectar la wake word.
   - *Ack hablado* si la acción tardará >1 s: "voy", "un segundo", "buscando..."
     (frases pregrabadas con Piper, coste cero).
   - *Estado visual* en el tray/overlay: escuchando / pensando / hablando.
3. **TTS en streaming**: el LLM emite tokens → se corta por frases → Piper
   sintetiza la frase N mientras suena la N-1. Nunca esperar al texto completo.
4. **STT incremental**: con Vosk se puede transcribir *mientras hablas*;
   faster-whisper arranca en cuanto el VAD detecta el fin. Valorar transcribir
   en paralelo con ambos y usar Vosk si el comando matchea el fast path.
5. **Acciones en workers**: nada bloquea el hilo de escucha. Si una búsqueda
   tarda, el asistente lo dice y sigue escuchando.
6. **Caché**: respuestas TTS de frases fijas pregeneradas en disco (saludos,
   acks, errores); resultados del tiempo cacheados 10 min.
7. **Timeouts con voz**: si algo externo (red, IMAP) tarda >5 s → "esto está
   tardando, te aviso cuando lo tenga" y se resuelve en background con
   notificación.

## Ajustes por hardware (perfiles automáticos)

- Al arrancar, el **gestor de perfiles** detecta VRAM/RAM/CPU y selecciona
  `full` / `gpu-lite` / `cpu` / `minimal` (tabla en docs/02, sección 6).
  Mismo código en todas las máquinas: el equipo de desarrollo sin GPU
  funciona igual, solo que con modelos más pequeños o sin LLM.
- `config.yaml`: `hardware.profile: auto` (por defecto) o forzado a un perfil
  concreto para pruebas ("¿cómo se comporta esto en un equipo flojo?").
- Los objetivos de latencia de arriba son para el perfil `full`; cada perfil
  degrada el *slow path*, nunca el fast path ni el feedback.
- Convivencia con juegos/apps GPU: si al arrancar una acción la VRAM libre es
  insuficiente, Ollama ya reparte capas a CPU solo; opcionalmente avisar
  ("voy un poco más lento, la gráfica está ocupada").

## Métricas desde el día 1

Loguear por interacción: t_wake, t_stt, t_route, t_action, t_first_audio.
Un `--debug` que lo imprima. Sin medir no se optimiza.
