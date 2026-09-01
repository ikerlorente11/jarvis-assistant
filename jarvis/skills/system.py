"""Sistema: volumen (pycaw), batería, capturas (mss), minimizar ventanas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import psutil


def _volume_control():
    from pycaw.pycaw import AudioUtilities

    return AudioUtilities.GetSpeakers().EndpointVolume


def _sin_voz(texto: str):
    """Confirmación evidente: se muestra pero no se dicta."""
    from jarvis.results import Rich

    return Rich(texto, speak="")


def volumen_subir(config: dict):
    vol = _volume_control()
    nivel = min(1.0, vol.GetMasterVolumeLevelScalar() + 0.10)
    vol.SetMasterVolumeLevelScalar(nivel, None)
    return _sin_voz(f"Volumen al {round(nivel * 100)}%.")


def volumen_bajar(config: dict):
    vol = _volume_control()
    nivel = max(0.0, vol.GetMasterVolumeLevelScalar() - 0.10)
    vol.SetMasterVolumeLevelScalar(nivel, None)
    return _sin_voz(f"Volumen al {round(nivel * 100)}%.")


def volumen_poner(config: dict, nivel: str):
    try:
        valor = int(nivel.strip().rstrip("%"))
    except ValueError:
        return f"«{nivel}» no es un porcentaje."
    valor = max(0, min(100, valor))
    _volume_control().SetMasterVolumeLevelScalar(valor / 100, None)
    return _sin_voz(f"Volumen al {valor}%.")


def silenciar(config: dict):
    vol = _volume_control()
    mute = not vol.GetMute()
    vol.SetMute(mute, None)
    return _sin_voz("Silenciado." if mute else "Sonido activado.")


def bateria(config: dict):
    from jarvis.results import Rich

    info = psutil.sensors_battery()
    if info is None:
        return "Este equipo no tiene batería."
    pct = round(info.percent)
    estado = "enchufada" if info.power_plugged else "usando batería"
    respuesta = f"Batería al {pct}% ({estado})."
    if not info.power_plugged and info.secsleft > 0:
        horas, resto = divmod(info.secsleft, 3600)
        respuesta += f" Quedan unas {horas} h {resto // 60} min."
    emoji = "🔌" if info.power_plugged else ("🔋" if pct > 20 else "🪫")
    color = "#2fae5f" if pct > 40 else ("#e8a13c" if pct > 15 else "#e05b4f")
    html = (
        f"<span style='font-size:26px'>{emoji}</span> "
        f"<span style='font-size:26px;color:{color};font-weight:bold'>{pct}%</span> "
        f"<span style='font-size:12px;color:#8fa3c4'>&nbsp;{estado}</span>"
    )
    return Rich(respuesta, html=html, speak=respuesta)


def captura(config: dict) -> str:
    import mss

    destino = Path.home() / "Pictures" / "Capturas"
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"captura-{datetime.now():%Y%m%d-%H%M%S}.png"
    with mss.mss() as sct:
        sct.shot(mon=-1, output=str(ruta))  # todos los monitores
    from jarvis.results import Item, Rich

    return Rich(
        "Captura guardada:",
        items=[Item("file", ruta.name, str(ruta))],
        speak="",
    )


def minimizar_todo(config: dict):
    import comtypes.client

    comtypes.client.CreateObject("Shell.Application").MinimizeAll()
    return _sin_voz("Ventanas minimizadas.")
