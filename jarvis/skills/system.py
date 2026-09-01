"""Sistema: volumen (pycaw), batería, capturas (mss), minimizar ventanas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import psutil


def _volume_control():
    from pycaw.pycaw import AudioUtilities

    return AudioUtilities.GetSpeakers().EndpointVolume


def volumen_subir(config: dict) -> str:
    vol = _volume_control()
    nivel = min(1.0, vol.GetMasterVolumeLevelScalar() + 0.10)
    vol.SetMasterVolumeLevelScalar(nivel, None)
    return f"Volumen al {round(nivel * 100)}%."


def volumen_bajar(config: dict) -> str:
    vol = _volume_control()
    nivel = max(0.0, vol.GetMasterVolumeLevelScalar() - 0.10)
    vol.SetMasterVolumeLevelScalar(nivel, None)
    return f"Volumen al {round(nivel * 100)}%."


def volumen_poner(config: dict, nivel: str) -> str:
    try:
        valor = int(nivel.strip().rstrip("%"))
    except ValueError:
        return f"«{nivel}» no es un porcentaje."
    valor = max(0, min(100, valor))
    _volume_control().SetMasterVolumeLevelScalar(valor / 100, None)
    return f"Volumen al {valor}%."


def silenciar(config: dict) -> str:
    vol = _volume_control()
    mute = not vol.GetMute()
    vol.SetMute(mute, None)
    return "Silenciado." if mute else "Sonido activado."


def bateria(config: dict) -> str:
    info = psutil.sensors_battery()
    if info is None:
        return "Este equipo no tiene batería."
    estado = "cargando" if info.power_plugged else "descargando"
    respuesta = f"Batería al {round(info.percent)}% ({estado})."
    if not info.power_plugged and info.secsleft > 0:
        horas, resto = divmod(info.secsleft, 3600)
        respuesta += f" Quedan unas {horas} h {resto // 60} min."
    return respuesta


def captura(config: dict) -> str:
    import mss

    destino = Path.home() / "Pictures" / "Capturas"
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"captura-{datetime.now():%Y%m%d-%H%M%S}.png"
    with mss.mss() as sct:
        sct.shot(mon=-1, output=str(ruta))  # todos los monitores
    return f"Captura guardada en {ruta}."


def minimizar_todo(config: dict) -> str:
    import comtypes.client

    comtypes.client.CreateObject("Shell.Application").MinimizeAll()
    return "Ventanas minimizadas."
