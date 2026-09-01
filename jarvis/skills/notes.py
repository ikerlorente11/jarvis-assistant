"""Notas rápidas en un markdown de Documentos."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

RUTA = Path.home() / "Documents" / "notas-jarvis.md"


def crear(config: dict, texto: str) -> str:
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    with RUTA.open("a", encoding="utf-8") as f:
        f.write(f"- [{datetime.now():%d/%m %H:%M}] {texto.strip()}\n")
    return f"Apuntado: «{texto.strip()}»."


def leer(config: dict) -> str:
    if not RUTA.exists():
        return "No hay notas todavía."
    lineas = [l for l in RUTA.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lineas:
        return "No hay notas todavía."
    ultimas = "\n".join(lineas[-5:])
    return f"Últimas notas:\n{ultimas}"
