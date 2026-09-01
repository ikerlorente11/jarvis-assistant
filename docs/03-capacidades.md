# 03 — Catálogo de capacidades

Cada capacidad indica su ruta: **[F]** fast path (sin IA, respuesta <1.5 s) o
**[L]** slow path (necesita LLM). Muchas son [F] con fallback [L] cuando la
frase es ambigua.

## Programas y ventanas

- [F] Abrir/cerrar programas por nombre o alias ("abre el navegador")
- [F] **Perfiles**: "modo trabajo" → abre VS Code + navegador + terminal de golpe
- [F] Cambiar de ventana, minimizar todo, cerrar la ventana activa
- [F] Abrir URLs frecuentes ("abre YouTube", "abre el correo")

## Archivos y carpetas

- [F] Abrir carpetas conocidas (Descargas, proyecto X, alias configurables)
- [F] Buscar archivos por nombre vía Everything ("busca la factura de marzo") → abre o dicta resultados
- [L] Búsquedas descritas en lenguaje natural ("el PDF que descargué ayer sobre impuestos")
- [F] "Haz una captura de pantalla", "abre la papelera"

## Tareas, tiempo y recordatorios

- [F] Hora, fecha, "¿qué día es el jueves?"
- [F] Timers y alarmas ("avísame en 20 minutos")
- [F/L] Recordatorios con fecha ("recuérdame el lunes a las 9 llamar al gestor") — el parseo de fechas raras cae al LLM
- [F/L] Tareas programadas recurrentes ("todos los viernes a las 5 ábreme el resumen semanal")
- [F] Listar/cancelar recordatorios pendientes

## Comunicación

- [L] Enviar correos ("mándale un correo a Juan diciendo que llego tarde" — el LLM redacta, **te lo lee y pide confirmación antes de enviar**)
- [F] Leer correos nuevos (asunto + remitente por IMAP)
- [F] Contactos frecuentes con alias en config

## Información

- [F] Tiempo/clima actual y previsión (Open-Meteo, sin clave)
- [F] Noticias: titulares de tus feeds RSS
- [L] Preguntas generales ("¿cuántos habitantes tiene Japón?") → Qwen3 local
- [L] Definiciones, traducciones, resúmenes de texto copiado ("resume lo que hay en el portapapeles")
- [F] Cálculos y conversiones ("cuánto es 15% de 340", "300 dólares a euros"*)

*Cambio de divisa: API gratuita de frankfurter.app (sin clave).

## Sistema

- [F] Volumen: subir/bajar/mutear; brillo
- [F] Música: play/pausa/siguiente (teclas multimedia — funciona con Spotify, etc.)
- [F] Bloquear equipo, suspender, apagar/reiniciar (**con confirmación por voz**)
- [F] "¿Cuánta batería queda?", "¿está cargando?"
- [F] Wi-Fi on/off, estado de red

## Dictado y notas

- [F] "Toma nota: ..." → apunta en un archivo de notas con timestamp
- [F] "Dicta" → transcribe lo que hables al portapapeles o a la app activa
- [F] "Lee mis notas de hoy"

## Conversación y control del asistente

- [F] "Para" / "cállate" → interrumpe el TTS al instante
- [F] "Repite", "más despacio"
- [L] Conversación con contexto: recordar las últimas N interacciones ("¿y mañana?" tras preguntar el tiempo)
- [F] "¿Qué sabes hacer?" → lista capacidades

## Ideas futuras (fuera del MVP)

- Control de domótica (Home Assistant local, API REST gratuita)
- Resumen de página web abierta / "léeme este artículo"
- Integración calendario (CalDAV / archivo .ics local)
- Visión: "¿qué hay en mi pantalla?" con un modelo multimodal local (Qwen3-VL)
