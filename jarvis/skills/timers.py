"""Timers en memoria con aviso por notificación toast.

Los recordatorios persistentes (sobreviven reinicios) llegan en fase 4 con
APScheduler; esto cubre el "avísame en 10 minutos" del día a día.
"""

from __future__ import annotations

import re
import threading

_activos: list[threading.Timer] = []


def crear(config: dict, tiempo: str, texto: str = "¡Tiempo cumplido!") -> str:
    match = re.match(r"(\d+)\s*(segundos?|minutos?|horas?|min|s|h)?", tiempo.strip())
    if not match:
        return f"No entiendo el tiempo «{tiempo}» (ej.: 10 minutos)."
    cantidad = int(match.group(1))
    unidad = (match.group(2) or "minutos")[0]  # s/m/h
    segundos = cantidad * {"s": 1, "m": 60, "h": 3600}[unidad]

    timer = threading.Timer(segundos, _avisar, args=(texto,))
    timer.daemon = True
    timer.start()
    _activos.append(timer)

    unidades = {"s": "segundos", "m": "minutos", "h": "horas"}[unidad]
    return f"Te aviso en {cantidad} {unidades}."


def _avisar(texto: str) -> None:
    from winotify import Notification, audio

    aviso = Notification(
        app_id="JARVIS", title="⏰ Temporizador", msg=texto, duration="long"
    )
    aviso.set_audio(audio.Default, loop=False)
    aviso.show()
