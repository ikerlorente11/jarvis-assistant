"""Prepara el texto para leerlo en voz alta: lo que se ve escrito no
siempre es lo que se debe decir (símbolos, unidades, rutas, emojis).
"""

from __future__ import annotations

import re
from pathlib import Path

DIAS = {
    "lun": "lunes", "mar": "martes", "mié": "miércoles", "jue": "jueves",
    "vie": "viernes", "sáb": "sábado", "dom": "domingo",
}

UNIDADES = [
    (re.compile(r"(\d+)\s*-\s*(\d+)\s*°C?"), r"\1 a \2 grados"),
    (re.compile(r"(\d+)\s*°C"), r"\1 grados"),
    (re.compile(r"(\d+)\s*°"), r"\1 grados"),
    (re.compile(r"(\d+)\s*km/h"), r"\1 kilómetros por hora"),
    (re.compile(r"(\d+)\s*%"), r"\1 por ciento"),
]


def _hora_hablada(match: re.Match) -> str:
    """8:51 → "8 y 51"; 11:00 → "11 en punto"; 9:05 → "9 y 5"."""
    hora, minutos = match.group(1), int(match.group(2))
    if minutos == 0:
        return f"{hora} en punto"
    if minutos == 15:
        return f"{hora} y cuarto"
    if minutos == 30:
        return f"{hora} y media"
    return f"{hora} y {minutos}"

RUTA = re.compile(r"[A-Za-z]:\\[^\s,;«»]+")
SIMBOLOS = re.compile(r"[*_`#\"«»“”\[\]|]")
EMOJIS = re.compile(
    "[\U0001f000-\U0001faff←-⇿⌀-➿⬀-⯿️]"
)


def normalizar(texto: str, replacements: dict | None = None) -> str:
    """Texto en pantalla → texto para pronunciar."""
    # rutas: se dice solo el nombre del archivo/carpeta
    texto = RUTA.sub(lambda m: Path(m.group(0)).name, texto)
    texto = re.sub(r"\b(\d{1,2}):(\d{2})\b", _hora_hablada, texto)
    for patron, reemplazo in UNIDADES:
        texto = patron.sub(reemplazo, texto)
    # unidades repetidas en la misma frase: "máxima 31 grados, mínima 16
    # grados" → la segunda sobra
    texto = re.sub(
        r"(grados|por ciento|kilómetros por hora)([^.!?]*?\d+) \1", r"\1\2", texto
    )
    # abreviaturas de días en la previsión ("mar 2:" → "martes 2:")
    texto = re.sub(
        r"\b(lun|mar|mié|jue|vie|sáb|dom)\b(?=\s+\d)",
        lambda m: DIAS[m.group(1)],
        texto,
    )
    texto = SIMBOLOS.sub("", texto)
    texto = EMOJIS.sub("", texto)
    # sustituciones del usuario (config tts.replacements) para palabras que
    # la voz pronuncie mal
    for palabra, dicho in (replacements or {}).items():
        texto = re.sub(rf"\b{re.escape(str(palabra))}\b", str(dicho), texto,
                       flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", texto.replace("\n", ". ")).strip()
