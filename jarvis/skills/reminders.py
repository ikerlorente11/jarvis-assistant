"""Recordatorios persistentes: sobreviven a reinicios (fase 4).

APScheduler con almacén SQLite en data/jarvis.db. El planificador arranca
con el asistente y dispara notificaciones toast; si el equipo estaba
apagado a la hora del aviso, se lanza al arrancar (gracia de 12 h).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

_scheduler = None

EN_TIEMPO = re.compile(r"\ben (\d+)\s*(segundos?|minutos?|min|horas?|h)\b")
A_LAS = re.compile(r"\b(mañana|manana)?\s*a las (\d{1,2})(?::(\d{2}))?\b")


def scheduler():
    """Planificador único; se crea (y rearma los trabajos pendientes) al
    primer uso. Llamado también desde el arranque del asistente."""
    global _scheduler
    if _scheduler is None:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.background import BackgroundScheduler

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _scheduler = BackgroundScheduler(
            jobstores={
                "default": SQLAlchemyJobStore(
                    url=f"sqlite:///{DATA_DIR / 'jarvis.db'}"
                )
            },
            job_defaults={"misfire_grace_time": 12 * 3600},
        )
        _scheduler.start()
    return _scheduler


def notificar(texto: str) -> None:
    """La ejecuta el planificador (debe ser importable a nivel de módulo)."""
    from winotify import Notification, audio

    aviso = Notification(
        app_id="JARVIS", title="🔔 Recordatorio", msg=texto, duration="long"
    )
    aviso.set_audio(audio.Reminder, loop=False)
    aviso.show()


def crear(config: dict, texto: str) -> str:
    cuando, mensaje = _parse(texto)
    if cuando is None:
        return ("No entiendo cuándo. Ejemplos: «llamar al médico en 2 horas», "
                "«sacar la basura a las 21:30», «revisar el correo mañana a las 9».")
    if not mensaje:
        mensaje = "¡Recordatorio!"
    scheduler().add_job(
        notificar, "date", run_date=cuando, args=[mensaje], id=None
    )
    return f"Apuntado: «{mensaje}» — {_fecha_legible(cuando)}."


def listar(config: dict) -> str:
    trabajos = sorted(scheduler().get_jobs(), key=lambda j: j.next_run_time)
    if not trabajos:
        return "No tienes recordatorios pendientes."
    lineas = [
        f"{n}. {job.args[0]} — {_fecha_legible(job.next_run_time)}"
        for n, job in enumerate(trabajos, 1)
    ]
    plural = "s" if len(trabajos) != 1 else ""
    return (f"Tienes {len(trabajos)} recordatorio{plural}:\n" + "\n".join(lineas))


def borrar(config: dict, numero: str) -> str:
    trabajos = sorted(scheduler().get_jobs(), key=lambda j: j.next_run_time)
    try:
        indice = int(numero.strip()) - 1
        job = trabajos[indice]
    except (ValueError, IndexError):
        return f"No hay recordatorio número «{numero}» (mira «mis recordatorios»)."
    mensaje = job.args[0]
    job.remove()
    return f"Borrado: «{mensaje}»."


def _parse(texto: str) -> tuple[datetime | None, str]:
    """Extrae el momento y deja el resto como mensaje."""
    texto = texto.strip()
    bajo = texto.lower()
    ahora = datetime.now()

    match = EN_TIEMPO.search(bajo)
    if match:
        cantidad = int(match.group(1))
        unidad = match.group(2)[0]  # s/m/h
        delta = timedelta(seconds=cantidad * {"s": 1, "m": 60, "h": 3600}[unidad])
        return ahora + delta, _limpiar(texto, match)

    match = A_LAS.search(bajo)
    if match:
        hora, minuto = int(match.group(2)), int(match.group(3) or 0)
        if not (0 <= hora <= 23 and 0 <= minuto <= 59):
            return None, ""
        cuando = ahora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if match.group(1):  # "mañana"
            cuando += timedelta(days=1)
        elif cuando <= ahora:  # las 9 ya pasaron → mañana a las 9
            cuando += timedelta(days=1)
        return cuando, _limpiar(texto, match)

    return None, ""


def _limpiar(texto: str, match: re.Match) -> str:
    mensaje = (texto[: match.start()] + texto[match.end():]).strip(" ,.")
    mensaje = re.sub(r"^(que|de)\s+", "", mensaje, flags=re.IGNORECASE)
    return mensaje.strip()


def _fecha_legible(cuando: datetime) -> str:
    hoy = datetime.now().date()
    fecha = cuando.date()
    if fecha == hoy:
        dia = "hoy"
    elif fecha == hoy + timedelta(days=1):
        dia = "mañana"
    else:
        dia = f"el {cuando.day:02d}/{cuando.month:02d}"
    return f"{dia} a las {cuando.hour}:{cuando.minute:02d}"
