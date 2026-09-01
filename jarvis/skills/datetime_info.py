"""Hora y fecha (stdlib, sin dependencias)."""

from __future__ import annotations

from datetime import datetime

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def hora(config: dict) -> str:
    now = datetime.now()
    return f"Son las {now.hour}:{now.minute:02d}."


def fecha(config: dict) -> str:
    now = datetime.now()
    return f"Hoy es {DIAS[now.weekday()]}, {now.day} de {MESES[now.month - 1]} de {now.year}."
