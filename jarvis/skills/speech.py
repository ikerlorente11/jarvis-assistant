"""Control por comandos de la voz del asistente (TTS).

La instancia de TTS la deja la UI en config["_tts"]; sin UI (tests, CLI)
estas skills avisan en vez de romper.
"""

from __future__ import annotations

from jarvis import config as config_module


def _tts(config: dict):
    return config.get("_tts")


def activar(config: dict) -> str:
    tts = _tts(config)
    if tts is None:
        return "La voz solo está disponible con la interfaz abierta."
    if not tts.available:
        return "No encuentro la voz de Piper en models/piper (ejecuta install.ps1)."
    tts.set_enabled(True)
    config_module.save_local({"tts": {"enabled": True}})
    return "Voz activada."


def desactivar(config: dict) -> str:
    tts = _tts(config)
    if tts is None:
        return "La voz solo está disponible con la interfaz abierta."
    tts.set_enabled(False)
    config_module.save_local({"tts": {"enabled": False}})
    return "Voz desactivada."


def volumen(config: dict, nivel: str) -> str:
    tts = _tts(config)
    if tts is None:
        return "La voz solo está disponible con la interfaz abierta."
    try:
        valor = int(nivel.strip().rstrip("%"))
    except ValueError:
        return f"«{nivel}» no es un porcentaje."
    tts.set_volume(valor)
    config_module.save_local({"tts": {"volume": tts.volume}})
    return f"Voz al {tts.volume}%."
