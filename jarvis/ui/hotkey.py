"""Atajo de teclado global: abre el asistente aunque la bolita esté oculta.

RegisterHotKey de Windows sobre el hilo de la UI + filtro de eventos
nativos de Qt para cazar el WM_HOTKEY. Sin dependencias.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

WM_HOTKEY = 0x0312
HOTKEY_ID = 1
MOD_NOREPEAT = 0x4000
MODS = {"ctrl": 0x2, "control": 0x2, "alt": 0x1, "shift": 0x4, "win": 0x8, "meta": 0x8}


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, app, callback):
        super().__init__()
        self._callback = callback
        self._registered = False
        app.installNativeEventFilter(self)

    def register(self, combo: str) -> bool:
        """Registra la combinación ("ctrl+alt+j"); False si no es válida o
        ya la usa otro programa."""
        user32 = ctypes.windll.user32
        if self._registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            self._registered = False
        parsed = self._parse(combo)
        if parsed is None:
            return False
        mods, vk = parsed
        self._registered = bool(
            user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, vk)
        )
        return self._registered

    @staticmethod
    def _parse(combo: str) -> tuple[int, int] | None:
        mods = 0
        vk = None
        for token in combo.lower().replace(" ", "").split("+"):
            if token in MODS:
                mods |= MODS[token]
            elif len(token) == 1 and token.isalnum():
                vk = ord(token.upper())
            elif token.startswith("f") and token[1:].isdigit():
                n = int(token[1:])
                if 1 <= n <= 12:
                    vk = 0x70 + n - 1  # VK_F1..F12
            elif token in ("espacio", "space"):
                vk = 0x20
        if vk is None or mods == 0:
            return None
        return mods, vk

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._callback()
        return False, 0
