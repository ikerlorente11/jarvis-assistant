"""Abrir URLs y sitios en el navegador predeterminado."""

from __future__ import annotations

import os
import re

DOMINIO = re.compile(r"^[\w.-]+\.[a-z]{2,}(/\S*)?$", re.IGNORECASE)


def abrir(config: dict, url: str) -> str:
    alias = config.get("sites", {})
    destino = alias.get(url.strip().lower(), url.strip())

    if not destino.startswith(("http://", "https://")):
        if not DOMINIO.match(destino):
            # "abre la web de marca" → búsqueda simple: dominio .com probable
            destino = destino.replace(" ", "")
            if not DOMINIO.match(destino + ".com"):
                return f"«{url}» no parece una dirección web."
            destino += ".com"
        destino = "https://" + destino

    from jarvis.results import Rich

    os.startfile(destino)  # el esquema http lo abre el navegador predeterminado
    visible = destino.removeprefix("https://").removeprefix("http://")
    return Rich(f"Abriendo {visible}.", speak="")
