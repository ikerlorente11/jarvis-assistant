"""Hora y fecha (stdlib, sin dependencias)."""

from __future__ import annotations

from datetime import datetime

from jarvis.results import Rich

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def hora(config: dict) -> Rich:
    now = datetime.now()
    texto = f"Son las {now.hour}:{now.minute:02d}."
    html = (
        f"<span style='font-size:30px;color:#f0f4fb;font-weight:bold'>"
        f"🕐 {now.hour}:{now.minute:02d}</span>"
    )
    return Rich(texto, html=html, speak=texto)


def fecha(config: dict) -> Rich:
    now = datetime.now()
    texto = f"Hoy es {DIAS[now.weekday()]}, {now.day} de {MESES[now.month - 1]} de {now.year}."
    html = (
        f"<span style='font-size:20px;color:#f0f4fb;font-weight:bold'>"
        f"📅 {DIAS[now.weekday()].capitalize()}, {now.day} de {MESES[now.month - 1]}</span>"
        f"<br><span style='font-size:12px;color:#8fa3c4'>{now.year}</span>"
    )
    return Rich(texto, html=html, speak=texto)
