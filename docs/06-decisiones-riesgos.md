# 06 — Decisiones abiertas y riesgos

## Decisiones que hay que tomar antes de la Fase 1

| Decisión | Opciones | Recomendación |
|---|---|---|
| ~~Hardware~~ **RESUELTO** | Equipo objetivo: RTX 3080 Ti 12 GB → perfil `full`. Desarrollo en otras máquinas → autodetección de perfiles (docs/02 §6) | El código nunca asume GPU: todo pasa por el gestor de perfiles |
| Palabra de activación | Modelo preentrenado ("hey Jarvis" existe en openWakeWord) vs entrenar una propia | Decidir en Fase 5 (voz aplazada hasta tener micrófono); empezar con el preentrenado |
| Voz del asistente | Voces es_ES de Piper (probar 3-4) | Elegir a oído en Fase 0 |
| Proveedor de correo | Gmail (contraseña de aplicación) vs Outlook | El que ya uses |
| Idioma de los comandos | Solo español vs bilingüe | Solo español al principio (simplifica intents) |

## Riesgos y mitigaciones

1. **Máquinas de desarrollo sin GPU** → el slow path puede irse a 4-6 s o no
   estar disponible. *Mitigación*: gestor de perfiles con autodetección
   (docs/02 §6) — perfiles `cpu`/`minimal` con modelos pequeños o LLM
   desactivado, fast path amplio y feedback hablado. El código nunca asume
   que hay GPU.
2. **Falsos positivos del wake word** (se activa solo).
   *Mitigación*: umbral ajustable en config + earcon para que siempre sepas
   que escucha + "cancela".
3. **STT falla con ruido/acento** → intents no reconocidos.
   *Mitigación*: rapidfuzz con umbral, "¿has dicho X?" en vez de fallar en
   silencio, y logs de frases fallidas para mejorar la tabla de intents.
4. **Acciones peligrosas por error** (apagar, enviar correo).
   *Mitigación*: lista de acciones que SIEMPRE piden confirmación por voz.
5. **Windows vs WSL2**: tocar audio y escritorio desde WSL2 es un callejón.
   *Decisión ya tomada*: el runtime vive en Windows nativo (ver docs/01).
6. **Modelos openWakeWord preentrenados son CC-BY-NC** (no comercial).
   OK para uso personal; si algún día se distribuye, entrenar modelos propios.
7. **Dependencia de APIs externas gratuitas** (Open-Meteo, frankfurter).
   *Mitigación*: caché + respuesta degradada ("no tengo conexión") — el resto
   del asistente funciona 100% offline.

## Qué NO vamos a hacer (por ahora)

- Nada de servicios de pago ni claves de API de pago.
- Nada de cloud STT/TTS/LLM: privacidad y coste cero son requisito.
- No reinventar un framework de asistentes completo (Rhasspy/OVOS existen,
  pero son pesados y menos flexibles que un pipeline propio de ~1000 líneas).
