"""Abrir carpetas: carpetas conocidas del usuario + alias de config.yaml."""

from __future__ import annotations

import os
from pathlib import Path

CONOCIDAS = {
    "descargas": "Downloads",
    "documentos": "Documents",
    "escritorio": "Desktop",
    "imágenes": "Pictures",
    "imagenes": "Pictures",
    "música": "Music",
    "musica": "Music",
    "vídeos": "Videos",
    "videos": "Videos",
}


def abrir(config: dict, carpeta: str) -> str:
    alias = config.get("folders", {})
    nombre = carpeta.strip().lower()

    ruta = alias.get(nombre)
    if ruta is None and nombre in CONOCIDAS:
        ruta = Path.home() / CONOCIDAS[nombre]
    if ruta is None and Path(nombre).expanduser().is_dir():
        ruta = nombre

    if ruta is None:
        return f"No conozco la carpeta «{carpeta}»."
    ruta = Path(ruta).expanduser()
    if not ruta.is_dir():
        return f"La carpeta «{ruta}» no existe."
    os.startfile(ruta)
    return f"Abriendo {carpeta}."
