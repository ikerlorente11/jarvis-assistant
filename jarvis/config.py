"""Carga de config.yaml (+ config.local.yaml, gitignored, que lo sobrescribe)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load() -> dict:
    config: dict = {}
    for name in ("config.yaml", "config.local.yaml"):
        path = ROOT / name
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            _merge(config, data)
    return config


def _merge(base: dict, extra: dict) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def delete_local(seccion: str, clave: str) -> bool:
    """Borra una clave añadida por el usuario en config.local.yaml.
    False si no estaba ahí (p. ej. viene del config.yaml base)."""
    path = ROOT / "config.local.yaml"
    if not path.exists():
        return False
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if seccion not in data or clave not in (data[seccion] or {}):
        return False
    del data[seccion][clave]
    if not data[seccion]:
        del data[seccion]
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return True


def save_local(updates: dict) -> None:
    """Persiste ajustes del usuario en config.local.yaml (gitignored),
    que pisa a config.yaml al cargar. Ej.: volumen de la voz."""
    path = ROOT / "config.local.yaml"
    current: dict = {}
    if path.exists():
        current = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _merge(current, updates)
    path.write_text(
        yaml.safe_dump(current, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
