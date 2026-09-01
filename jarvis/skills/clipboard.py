"""Portapapeles: leer lo copiado."""

from __future__ import annotations

import pyperclip


def leer(config: dict) -> str:
    texto = pyperclip.paste().strip()
    if not texto:
        return "El portapapeles está vacío."
    if len(texto) > 400:
        texto = texto[:400] + "…"
    return f"Portapapeles:\n{texto}"
