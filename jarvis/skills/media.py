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


def play_pausa(config: dict) -> str:
    _pulsar(VK_MEDIA_PLAY_PAUSE)
    return "▶⏸"


def siguiente(config: dict) -> str:
    _pulsar(VK_MEDIA_NEXT)
    return "⏭ Siguiente."


def anterior(config: dict) -> str:
    _pulsar(VK_MEDIA_PREV)
    return "⏮ Anterior."
