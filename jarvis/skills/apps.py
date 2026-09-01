"""Abrir programas: alias de config.yaml o nombre directo.

os.startfile usa ShellExecute: resuelve ejecutables del PATH y programas
registrados (App Paths: chrome, notepad...), no bloquea y falla al instante
si no existe.
"""

from __future__ import annotations

import os


def abrir(config: dict, app: str) -> str:
    alias = config.get("apps", {})
    nombre = app.strip().lower()
    objetivo = alias.get(nombre, nombre)
    try:
        os.startfile(objetivo)
    except OSError:
        return f"No he encontrado el programa «{app}»."
    return f"Abriendo {app}."
