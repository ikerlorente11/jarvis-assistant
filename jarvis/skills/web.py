"""Navegador: abrir URLs y buscar en internet.

Ambas órdenes admiten sufijos: «… en la pantalla principal/secundaria/N»
(ventana nueva movida a ese monitor) y «… en una ventana nueva».
"""

from __future__ import annotations

import os
import re
from urllib.parse import quote_plus

DOMINIO = re.compile(r"^[\w.-]+\.[a-z]{2,}(/\S*)?$", re.IGNORECASE)
PANTALLA = re.compile(
    r"\s+en (?:la |una )?pantalla (principal|primaria|secundaria|\d+)\s*$",
    re.IGNORECASE,
)
VENTANA = re.compile(r"\s+en (?:una )?ventana nueva\s*$", re.IGNORECASE)


def _extraer_sufijos(texto: str) -> tuple[str, str | None, bool]:
    """→ (texto limpio, pantalla, ventana_nueva)."""
    pantalla = None
    nueva = False
    match = PANTALLA.search(texto)
    if match:
        pantalla = match.group(1).lower()
        texto = texto[: match.start()]
    match = VENTANA.search(texto)
    if match:
        nueva = True
        texto = texto[: match.start()]
    return texto.strip(), pantalla, nueva


def _lanzar(config: dict, url: str, pantalla: str | None, nueva: bool,
            etiqueta: str):
    from jarvis.results import Rich
    from jarvis.skills.apps import _default_browser
    from jarvis.skills.screens import abrir_en_pantalla

    if pantalla or nueva:
        navegador = _default_browser()
        if navegador:
            aviso = abrir_en_pantalla(navegador, url, pantalla)
            donde = f" en la pantalla {pantalla}" if pantalla else " en ventana nueva"
            texto = aviso or f"Abriendo {etiqueta}{donde}."
            return Rich(texto, speak="")
    os.startfile(url)  # el esquema http lo abre el navegador predeterminado
    return Rich(f"Abriendo {etiqueta}.", speak="")


def abrir(config: dict, url: str):
    destino, pantalla, nueva = _extraer_sufijos(url)
    destino = destino.strip(" .")  # puntuación colada del dictado
    alias = config.get("sites", {}) or {}
    destino = alias.get(destino.lower(), destino)
    if not destino.startswith(("http://", "https://")):
        if not DOMINIO.match(destino):
            candidato = destino.replace(" ", "").strip(".")
            if DOMINIO.match(candidato):  # "youtube . com" dictado con pausas
                destino = candidato
            elif "." not in candidato and DOMINIO.match(candidato + ".com"):
                destino = candidato + ".com"
            else:
                # no parece una dirección: lo buscamos en internet
                return buscar(config, url)
        destino = "https://" + destino
    etiqueta = destino.removeprefix("https://").removeprefix("http://")
    return _lanzar(config, destino, pantalla, nueva, etiqueta)


def buscar(config: dict, consulta: str):
    texto, pantalla, nueva = _extraer_sufijos(consulta)
    if not texto:
        return "¿Qué quieres que busque en internet?"
    url = "https://www.google.com/search?q=" + quote_plus(texto)
    return _lanzar(config, url, pantalla, nueva, f"la búsqueda «{texto}»")
