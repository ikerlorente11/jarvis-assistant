"""Abrir programas por aproximación.

Orden de resolución:
1. Alias de config.yaml (navegador → default-browser, notas → notepad...).
2. Fuzzy sobre el índice de programas instalados (accesos del menú Inicio
   de usuario y máquina + App Paths del registro): "notepadd++" → Notepad++.
3. Ejecutable directo (os.startfile resuelve PATH y App Paths).
4. Si parece un dominio (tiene punto), se abre como URL.
"""

from __future__ import annotations

import functools
import os
import re
import winreg
from pathlib import Path

from rapidfuzz import fuzz, process

FUZZY_CUTOFF = 75

START_MENUS = (
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
)

EXCLUIR = ("uninstall", "desinstalar", "readme", "ayuda de", "documentation", "website")


def abrir(config: dict, app: str) -> str:
    alias = config.get("apps", {})
    nombre = app.strip().lower()
    objetivo = alias.get(nombre, nombre)

    from jarvis.results import Rich

    def abierto(nombre: str) -> Rich:
        # acción evidente elegida por el usuario: se muestra, no se dicta
        return Rich(f"Abriendo {nombre}.", speak="")

    if objetivo == "default-browser":
        exe = _default_browser()
        if exe is None:
            return "No he podido averiguar el navegador predeterminado."
        os.startfile(exe)
        return abierto("el navegador")

    # Fuzzy sobre lo instalado: tolera errores de escritura. Con un match
    # claro se abre; con varios dudosos se ofrece elegir.
    from jarvis.results import Item

    indice = _installed_apps()
    candidatos = process.extract(
        objetivo,
        list(indice.keys()),
        scorer=fuzz.WRatio,
        score_cutoff=FUZZY_CUTOFF,
        limit=5,
    )
    if candidatos:
        mejor, puntuacion = candidatos[0][0], candidatos[0][1]
        claro = puntuacion >= 90 and (
            len(candidatos) == 1 or candidatos[1][1] <= puntuacion - 8
        )
        if claro or len(candidatos) == 1:
            os.startfile(indice[mejor])
            return abierto(mejor)
        items = [Item("app", nombre, indice[nombre]) for nombre, _, _ in candidatos]
        return Rich(
            f"He encontrado varios programas parecidos a «{app}», elige:",
            items,
            speak="",
        )

    try:
        os.startfile(objetivo)
        return abierto(app)
    except OSError:
        pass

    if "." in objetivo and " " not in objetivo:  # parece un dominio
        from jarvis.skills import web

        return web.abrir(config, url=objetivo)

    return f"No he encontrado el programa «{app}»."


def modo(config: dict, perfil: str):
    """Perfiles: "modo trabajo" ejecuta las órdenes del perfil. Cada entrada
    puede ser una orden completa del router ("el tiempo en logroño") o un
    nombre de programa/web a abrir."""
    from jarvis.results import Rich

    perfiles = config.get("app_profiles", {})
    nombre = perfil.strip().lower()
    match = process.extractOne(
        nombre, list(perfiles.keys()), scorer=fuzz.WRatio, score_cutoff=FUZZY_CUTOFF
    )
    if not match:
        disponibles = ", ".join(perfiles) or "ninguno configurado"
        return f"No conozco el modo «{perfil}» (disponibles: {disponibles})."
    router = config.get("_router")
    hechas = []
    for orden in perfiles[match[0]]:
        if router is not None and router.matches(orden):
            resultado = router.handle(orden)
            hechas.append(f"✓ {orden} — {resultado.text.splitlines()[0][:60]}")
        else:
            resultado = abrir(config, orden)
            texto = resultado.text if hasattr(resultado, "text") else resultado
            hechas.append(f"✓ {orden} — {texto[:60]}")
    return Rich(f"Modo {match[0]}:\n" + "\n".join(hechas), speak="")


@functools.lru_cache(maxsize=1)
def _installed_apps() -> dict[str, str]:
    """nombre visible → ruta lanzable (.lnk del menú Inicio o exe de App Paths)."""
    indice: dict[str, str] = {}
    for exe, ruta in _app_paths():
        indice.setdefault(exe.removesuffix(".exe"), ruta)
    for base in START_MENUS:
        if not base.is_dir():
            continue
        for lnk in base.rglob("*.lnk"):
            nombre = lnk.stem.lower()
            if any(p in nombre for p in EXCLUIR):
                continue
            indice[lnk.stem] = str(lnk)  # el .lnk pisa al exe: mejor nombre
    return indice


def _app_paths() -> list[tuple[str, str]]:
    resultado = []
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            key = winreg.OpenKey(
                root, r"Software\Microsoft\Windows\CurrentVersion\App Paths"
            )
        except OSError:
            continue
        with key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, sub) as subkey:
                        ruta = winreg.QueryValueEx(subkey, None)[0]
                    resultado.append((sub.lower(), ruta.strip('"')))
                except OSError:
                    continue
    return resultado


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
