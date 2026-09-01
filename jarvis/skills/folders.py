"""Abrir carpetas: conocidas/alias por aproximación y, si no, búsqueda real
con Everything (es.exe) — no hace falta saberse la ruta.
"""

from __future__ import annotations

import os
from pathlib import Path

from rapidfuzz import fuzz, process

from jarvis.skills.files import everything

FUZZY_CUTOFF = 78

CONOCIDAS = {
    "descargas": "Downloads",
    "documentos": "Documents",
    "escritorio": "Desktop",
    "imagenes": "Pictures",
    "musica": "Music",
    "videos": "Videos",
}


def abrir(config: dict, carpeta: str) -> str:
    nombre = carpeta.strip().lower()
    candidatos = dict(config.get("folders", {}))
    for con, sub in CONOCIDAS.items():
        candidatos.setdefault(con, Path.home() / sub)

    # 1. Conocidas y alias, con tolerancia a erratas ("descargs").
    match = process.extractOne(
        nombre, list(candidatos.keys()), scorer=fuzz.WRatio, score_cutoff=FUZZY_CUTOFF
    )
    if match:
        ruta = Path(str(candidatos[match[0]])).expanduser()
        if ruta.is_dir():
            os.startfile(ruta)
            return f"Abriendo {match[0]}."

    # 2. Ruta literal.
    ruta = Path(nombre).expanduser()
    if ruta.is_dir():
        os.startfile(ruta)
        return f"Abriendo {ruta}."

    # 3. Everything: carpetas cuyo nombre contenga lo pedido. Ventana amplia:
    # con pocas, la carpeta de nombre exacto puede quedarse fuera.
    rutas = everything(config, f"folder:{nombre}", max_results=200)
    if rutas is None:
        return "No encuentro es.exe (Everything) para buscar carpetas."
    rutas = [r for r in rutas if Path(r).is_dir()]
    if not rutas:
        return f"No he encontrado ninguna carpeta «{carpeta}»."
    mejor = _mejor_carpeta(nombre, rutas)
    os.startfile(mejor)
    return f"Abriendo {mejor}."


def _mejor_carpeta(nombre: str, rutas: list[str]) -> str:
    """Mejor candidata: nombre más parecido; a igualdad, ruta menos profunda
    (C:/Proyectos gana a C:/x/y/z/Proyectos-backup)."""
    def clave(ruta: str) -> tuple:
        similitud = fuzz.WRatio(nombre, Path(ruta).name.lower())
        return (-similitud, ruta.count(os.sep), len(ruta))

    return min(rutas, key=clave)
