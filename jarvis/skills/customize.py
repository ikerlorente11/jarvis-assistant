"""Personalización por comandos: alias, contactos y modos sin tocar
config.yaml a mano. Todo se guarda en config.local.yaml y se aplica al
momento (la config en memoria es compartida).
"""

from __future__ import annotations

import re
from pathlib import Path

from jarvis import config as config_module

SEPARADORES = ("->", "→", "=", ":", " es ", " como ", " a ")
DOMINIO = re.compile(r"^[\w.-]+\.[a-z]{2,}(/\S*)?$", re.IGNORECASE)
ARTICULOS = ("de ", "del ", "nuevo ", "nueva ", "el ", "la ")


def _guardar(config: dict, seccion: str, clave: str, valor) -> None:
    config_module.save_local({seccion: {clave: valor}})
    config.setdefault(seccion, {})[clave] = valor


def alias(config: dict, datos: str) -> str:
    """«Ainhoa -> noah@gmail.com» → detecta solo si es contacto (email),
    web (dominio), carpeta (ruta) o programa (lo demás)."""
    nombre = valor = None
    for sep in SEPARADORES:
        if sep in datos:
            izquierda, derecha = datos.split(sep, 1)
            nombre, valor = izquierda.strip(), derecha.strip()
            break
    if not nombre or not valor:
        return ("Dímelo como «nombre -> destino». Ej.: Ainhoa -> "
                "noah@gmail.com · trabajo -> C:\\Proyectos · tube -> youtube.com")
    nombre = nombre.lower()
    for articulo in ARTICULOS:
        nombre = nombre.removeprefix(articulo)
    nombre = nombre.strip()

    if "@" in valor:
        _guardar(config, "contacts", nombre, valor)
        return f"Contacto guardado: {nombre} → {valor}."
    if valor.startswith(("http://", "https://")) or DOMINIO.match(valor):
        _guardar(config, "sites", nombre, valor)
        return f"Web guardada: «abre la web {nombre}» → {valor}."
    if "\\" in valor or "/" in valor or Path(valor).expanduser().is_dir():
        _guardar(config, "folders", nombre, valor)
        return f"Carpeta guardada: «abre la carpeta {nombre}» → {valor}."
    _guardar(config, "apps", nombre, valor)
    return f"Programa guardado: «abre {nombre}» → {valor}."


def modo(config: dict, datos: str) -> str:
    """«arranca con youtube.com y el tiempo en logroño» → modo con una
    lista de órdenes que se ejecutan con «modo arranca»."""
    encaje = re.match(r"\s*(\S+)\s+(?:con|para|:)\s+(.+)", datos, re.DOTALL)
    if not encaje:
        return ("Dímelo como «nombre con orden1, orden2…». Ej.: crea el modo "
                "arranca con youtube.com y el tiempo en logroño")
    nombre = encaje.group(1).lower()
    ordenes = [
        parte.strip(" .")
        for parte in re.split(r",| y luego | y ", encaje.group(2))
        if parte.strip(" .")
    ]
    if not ordenes:
        return "El modo necesita al menos una orden."

    router = config.get("_router")
    guardadas, avisos = [], []
    for orden in ordenes:
        guardadas.append(_afinar_orden(router, orden))
        if router is not None and not router.matches(guardadas[-1]) \
                and not DOMINIO.match(guardadas[-1]):
            avisos.append(guardadas[-1])
    _guardar(config, "app_profiles", nombre, guardadas)

    respuesta = (f"Modo «{nombre}» creado con {len(guardadas)} "
                 f"{'orden' if len(guardadas) == 1 else 'órdenes'}: "
                 + "; ".join(guardadas) + f". Actívalo con «modo {nombre}».")
    if avisos:
        respuesta += (" ⚠ No estoy seguro de entender: "
                      + "; ".join(avisos) + " (se intentará abrir como programa).")
    return respuesta


def _afinar_orden(router, orden: str) -> str:
    """Busca una variante de la orden que el router entienda de verdad."""
    if router is None:
        return orden
    variantes = [orden]
    for articulo in ("el ", "la ", "los ", "las "):
        if orden.lower().startswith(articulo):
            variantes.append(orden[len(articulo):])
    variantes.append(f"abre {orden}")
    for variante in variantes:
        if router.matches(variante):
            return variante
    return orden


def ver(config: dict) -> str:
    secciones = (
        ("Contactos", "contacts", "{k} → {v}"),
        ("Programas (alias)", "apps", "{k} → {v}"),
        ("Webs", "sites", "{k} → {v}"),
        ("Carpetas", "folders", "{k} → {v}"),
        ("Modos", "app_profiles", "{k}: {v}"),
    )
    bloques = []
    for titulo, clave, plantilla in secciones:
        entradas = config.get(clave) or {}
        if not entradas:
            continue
        lineas = "\n".join(
            "  • " + plantilla.format(
                k=k, v=", ".join(v) if isinstance(v, list) else v
            )
            for k, v in entradas.items()
        )
        bloques.append(f"{titulo}:\n{lineas}")
    if not bloques:
        return ("No tienes personalización todavía. Prueba: «añade el alias "
                "Ainhoa -> correo@gmail.com» o «crea el modo cine con "
                "youtube.com y baja el volumen».")
    from jarvis.results import Rich

    return Rich("\n".join(bloques), speak="Aquí tienes tu personalización.")