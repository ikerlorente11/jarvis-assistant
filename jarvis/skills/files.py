"""Buscar y abrir archivos con Everything (es.exe): índice NTFS instantáneo."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from rapidfuzz import fuzz

def _find_es(config: dict) -> str | None:
    """Localiza es.exe: config, PATH, o instalación de winget (cuyo directorio
    puede no estar aún en el PATH de este proceso)."""
    configurado = config.get("tools", {}).get("es")
    if configurado:
        return configurado
    en_path = shutil.which("es")
    if en_path:
        return en_path
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet"
    for candidato in (winget / "Links/es.exe", *winget.glob("Packages/voidtools.Everything.Cli*/es.exe")):
        if candidato.exists():
            return str(candidato)
    return None


def everything(config: dict, query: str, max_results: int = 10) -> list[str] | None:
    """Lanza es.exe y devuelve rutas; None si es.exe no está disponible."""
    es = _find_es(config)
    if es is None:
        return None
    completed = subprocess.run(
        [es, "-n", str(max_results), *query.split()],
        capture_output=True,
        text=True,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,  # sin parpadeo de consola
    )
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def buscar(config: dict, texto: str):
    from jarvis.results import Item, Rich

    rutas = everything(config, texto, max_results=8)
    if rutas is None:
        return "No encuentro es.exe (Everything) para buscar."
    if not rutas:
        return f"No he encontrado nada que contenga «{texto}»."
    items = [
        Item(
            kind="folder" if Path(r).is_dir() else "file",
            label=Path(r).name,
            path=r,
        )
        for r in rutas
    ]
    plural = "s" if len(items) != 1 else ""
    return Rich(f"He encontrado {len(items)} resultado{plural}:", items, speak="")


def abrir(config: dict, texto: str) -> str:
    """Busca y abre directamente el archivo que mejor encaje."""
    rutas = everything(config, f"file: {texto}", max_results=20)
    if rutas is None:
        return "No encuentro es.exe (Everything) para buscar."
    if not rutas:
        return f"No he encontrado ningún archivo «{texto}»."
    from jarvis.results import Rich

    mejor = max(rutas, key=lambda r: fuzz.WRatio(texto.lower(), Path(r).name.lower()))
    os.startfile(mejor)
    return Rich(f"Abriendo {mejor}.", speak="")
