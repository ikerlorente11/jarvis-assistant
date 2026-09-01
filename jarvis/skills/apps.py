"""Abrir programas: alias de config.yaml o nombre directo.

os.startfile usa ShellExecute: resuelve ejecutables del PATH y programas
registrados (App Paths: chrome, notepad...), no bloquea y falla al instante
si no existe.
"""

from __future__ import annotations

import os
import re
import winreg


def abrir(config: dict, app: str) -> str:
    alias = config.get("apps", {})
    nombre = app.strip().lower()
    objetivo = alias.get(nombre, nombre)

    if objetivo == "default-browser":
        exe = _default_browser()
        if exe is None:
            return "No he podido averiguar el navegador predeterminado."
        objetivo = exe

    try:
        os.startfile(objetivo)
    except OSError:
        return f"No he encontrado el programa «{app}»."
    return f"Abriendo {app}."


def _default_browser() -> str | None:
    """Ejecutable del navegador predeterminado, leído del registro."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations"
            r"\UrlAssociations\http\UserChoice",
        ) as key:
            progid = winreg.QueryValueEx(key, "ProgId")[0]
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, progid + r"\shell\open\command"
        ) as key:
            command = winreg.QueryValueEx(key, None)[0]
    except OSError:
        return None
    match = re.match(r'"([^"]+)"', command)
    return match.group(1) if match else command.split()[0]
