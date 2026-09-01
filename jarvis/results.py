"""Resultados ricos de las skills.

Una skill puede devolver un str (solo texto) o un Rich: texto + elementos
que la UI pinta como lista clicable (icono + nombre) con acciones útiles
(abrir, abrir la carpeta que lo contiene...).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    kind: str  # "file" | "folder" | "app" | "intent"
    label: str  # nombre visible (sin ruta)
    path: str  # qué abrir al pulsarlo (para "intent": el id a ejecutar)


@dataclass
class Rich:
    text: str  # respuesta en texto plano (fallback y para el LLM)
    items: list[Item] = field(default_factory=list)
    html: str | None = None  # tarjeta visual (la pinta la UI si existe)
    speak: str | None = None  # resumen para la voz (si no, se lee text)
