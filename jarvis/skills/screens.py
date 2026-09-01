"""Colocación de ventanas por monitor (API nativa de Windows).

Abre una ventana nueva del navegador y la mueve a la pantalla pedida:
se apuntan las ventanas del navegador antes de lanzar, y la que aparezca
nueva es la que se recoloca (maximizada en el monitor destino).
"""

from __future__ import annotations

import ctypes
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.windll.user32

SW_RESTORE = 9
SW_MAXIMIZE = 3
SWP_NOZORDER = 0x0004

CHROMIUM = ("brave", "chrome", "msedge", "opera", "vivaldi", "chromium")


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def monitores() -> list[dict]:
    """[{'work': (l, t, r, b), 'primary': bool}], principal primero."""
    resultado = []
    proc_type = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
    )

    def callback(hmon, _hdc, _rect, _lparam):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        work = info.rcWork
        resultado.append({
            "work": (work.left, work.top, work.right, work.bottom),
            "primary": bool(info.dwFlags & 1),
        })
        return 1

    user32.EnumDisplayMonitors(None, None, proc_type(callback), 0)
    return sorted(resultado, key=lambda m: not m["primary"])


def _monitor_destino(etiqueta: str) -> dict | None:
    todos = monitores()
    if not todos:
        return None
    if etiqueta in ("principal", "primaria", "1"):
        return todos[0]
    secundarios = [m for m in todos if not m["primary"]]
    if etiqueta in ("secundaria", "2"):
        return secundarios[0] if secundarios else None
    try:
        return todos[int(etiqueta) - 1]
    except (ValueError, IndexError):
        return None


def _ventanas_de(exe: str) -> set[int]:
    """Ventanas top-level visibles cuyo proceso es ese ejecutable."""
    import psutil

    pids = {
        p.pid for p in psutil.process_iter(["name"])
        if (p.info["name"] or "").lower() == exe.lower()
    }
    encontradas: set[int] = set()
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):  # GW_OWNER
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                encontradas.add(hwnd)
        return 1

    user32.EnumWindows(proc_type(callback), 0)
    return encontradas


def abrir_en_pantalla(navegador: str, url: str, pantalla: str | None,
                      timeout: float = 8.0) -> str | None:
    """Ventana nueva del navegador con la URL; si `pantalla`, la mueve allí
    maximizada. → None si todo bien, o un aviso."""
    exe = Path(navegador).name
    flag = "--new-window" if any(n in exe.lower() for n in CHROMIUM) else "-new-window"
    destino = _monitor_destino(pantalla) if pantalla else None
    if pantalla and destino is None:
        subprocess.Popen([navegador, flag, url])
        return f"Solo veo una pantalla: lo he abierto sin mover (pedías «{pantalla}»)."

    antes = _ventanas_de(exe) if destino else set()
    subprocess.Popen([navegador, flag, url])
    if destino is None:
        return None

    limite = time.monotonic() + timeout
    nueva = None
    while time.monotonic() < limite:
        aparecidas = _ventanas_de(exe) - antes
        if aparecidas:
            nueva = aparecidas.pop()
            break
        time.sleep(0.25)
    if nueva is None:
        return "He abierto la ventana pero no he podido localizarla para moverla."
    left, top, right, bottom = destino["work"]
    user32.ShowWindow(nueva, SW_RESTORE)
    user32.SetWindowPos(nueva, 0, left, top, right - left, bottom - top, SWP_NOZORDER)
    user32.ShowWindow(nueva, SW_MAXIMIZE)
    return None
