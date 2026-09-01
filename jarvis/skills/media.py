"""Teclas multimedia (play/pausa/siguiente/anterior) vía keybd_event.

Controla Spotify, YouTube, etc. sin API: son las mismas teclas del teclado.
"""

from __future__ import annotations

import ctypes

VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

KEYEVENTF_EXTENDEDKEY = 0x1
KEYEVENTF_KEYUP = 0x2


def _pulsar(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


def reproduciendo() -> bool | None:
    """True si hay música/vídeo sonando, False si está en pausa, None si no
    hay sesión multimedia (API de Windows: sesiones de transporte)."""
    try:
        import asyncio

        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )

        async def estado():
            sesion = (await Manager.request_async()).get_current_session()
            if sesion is None:
                return None
            return int(sesion.get_playback_info().playback_status) == 4  # PLAYING

        return asyncio.run(estado())
    except Exception:
        return None


def _silencioso(texto: str):
    from jarvis.results import Rich

    return Rich(texto, speak="")


def play_pausa(config: dict):
    _pulsar(VK_MEDIA_PLAY_PAUSE)
    return _silencioso("Play / pausa.")


def siguiente(config: dict):
    _pulsar(VK_MEDIA_NEXT)
    return _silencioso("Siguiente pista.")


def anterior(config: dict):
    _pulsar(VK_MEDIA_PREV)
    return _silencioso("Pista anterior.")
