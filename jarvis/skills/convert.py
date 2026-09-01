"""Conversor de unidades comunes (sin dependencias)."""

from __future__ import annotations

import re

# factor a la unidad base de cada familia
FACTORES = {
    # longitud (base: metro)
    "mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
    "in": 0.0254, "pulgadas": 0.0254, "ft": 0.3048, "pies": 0.3048,
    "millas": 1609.344, "mi": 1609.344, "yardas": 0.9144,
    # peso (base: kilogramo)
    "g": 0.001, "gramos": 0.001, "kg": 1.0, "kilos": 1.0,
    "lb": 0.453592, "libras": 0.453592, "oz": 0.0283495, "onzas": 0.0283495,
    "toneladas": 1000.0,
    # volumen (base: litro)
    "ml": 0.001, "l": 1.0, "litros": 1.0, "galones": 3.78541, "gal": 3.78541,
    "tazas": 0.24,
}
FAMILIA = {}
for unidades, familia in (
    (("mm", "cm", "m", "km", "in", "pulgadas", "ft", "pies", "millas", "mi", "yardas"), "longitud"),
    (("g", "gramos", "kg", "kilos", "lb", "libras", "oz", "onzas", "toneladas"), "peso"),
    (("ml", "l", "litros", "galones", "gal", "tazas"), "volumen"),
):
    for u in unidades:
        FAMILIA[u] = familia

EXPRESION = re.compile(
    r"([\d.,]+)\s*(°?[a-zñ]+)\s+(?:a|en)\s+(°?[a-zñ]+)", re.IGNORECASE
)


def convertir(config: dict, expresion: str) -> str:
    match = EXPRESION.search(expresion.strip().lower())
    if not match:
        return "Dímelo como «10 km a millas» o «100 f a c»."
    try:
        valor = float(match.group(1).replace(",", "."))
    except ValueError:
        return f"«{match.group(1)}» no es un número."
    origen, destino = _unidad(match.group(2)), _unidad(match.group(3))

    if {origen, destino} <= {"c", "f"}:  # temperatura, caso especial
        if origen == destino:
            resultado = valor
        elif origen == "c":
            resultado = valor * 9 / 5 + 32
        else:
            resultado = (valor - 32) * 5 / 9
        return f"{_num(valor)}°{origen.upper()} son {_num(resultado)}°{destino.upper()}."

    if origen not in FACTORES or destino not in FACTORES:
        desconocida = origen if origen not in FACTORES else destino
        return f"No conozco la unidad «{desconocida}»."
    if FAMILIA[origen] != FAMILIA[destino]:
        return f"No puedo convertir {FAMILIA[origen]} a {FAMILIA[destino]}."
    resultado = valor * FACTORES[origen] / FACTORES[destino]
    return f"{_num(valor)} {origen} son {_num(resultado)} {destino}."


def _unidad(u: str) -> str:
    u = u.lstrip("°")
    return {"celsius": "c", "fahrenheit": "f", "grados": "c"}.get(u, u)


def _num(n: float) -> str:
    return f"{n:g}" if abs(n) >= 0.01 else f"{n:.4f}"
