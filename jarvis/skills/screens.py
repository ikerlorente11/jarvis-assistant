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


# -- cerrar ventanas ----------------------------------------------------------

WM_CLOSE = 0x0010
VK_CONTROL, VK_W = 0x11, 0x57
KEYEVENTF_KEYUP = 0x0002

# En un navegador, el título de la ventana es el de la pestaña ACTIVA:
# si casa, se cierra solo esa pestaña (Ctrl+W), nunca la ventana entera.
NAVEGADORES = {
    "brave.exe", "chrome.exe", "msedge.exe", "firefox.exe",
    "opera.exe", "opera_gx.exe", "vivaldi.exe", "librewolf.exe",
}


def _exe_de(hwnd) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        import psutil

        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""


def _cerrar_pestana(hwnd) -> bool:
    """Trae la ventana al frente y manda Ctrl+W: cierra SOLO la pestaña
    activa. Respeta el estado (no desmaximiza) y devuelve el foco a la
    ventana donde estaba el usuario. False si Windows no da el foco."""
    kernel32 = ctypes.windll.kernel32
    anterior = user32.GetForegroundWindow()
    this_thread = kernel32.GetCurrentThreadId()
    fore_thread = user32.GetWindowThreadProcessId(anterior, None)
    user32.AttachThreadInput(this_thread, fore_thread, True)
    if user32.IsIconic(hwnd):  # solo si está minimizada (restore
        user32.ShowWindow(hwnd, SW_RESTORE)  # desmaximizaría las demás)
    user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(this_thread, fore_thread, False)
    time.sleep(0.2)
    if user32.GetForegroundWindow() != hwnd:
        return False
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_W, 0, 0, 0)
    user32.keybd_event(VK_W, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    if anterior and anterior != hwnd:
        time.sleep(0.15)
        user32.SetForegroundWindow(anterior)  # de vuelta donde estabas
    return True


def _ventanas_visibles() -> list[tuple[int, str]]:
    """[(hwnd, título)] de las ventanas visibles con título."""
    resultado: list[tuple[int, str]] = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buffer = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buffer, n + 1)
                resultado.append((hwnd, buffer.value))
        return 1

    user32.EnumWindows(proc_type(callback), 0)
    return resultado


def cerrar_ventana(config: dict, ventana: str):
    """Cierra la ventana cuyo título encaje con lo pedido («cierra la
    ventana de youtube»). Cierre educado (WM_CLOSE): la app puede
    preguntar si hay algo sin guardar."""
    import re

    from rapidfuzz import fuzz

    from jarvis.results import Rich

    objetivo = ventana.strip().lower()
    if objetivo in ("navegador", "el navegador"):  # este sí: entero
        cerradas = 0
        for hwnd, _titulo in _ventanas_visibles():
            if _exe_de(hwnd) in NAVEGADORES:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                cerradas += 1
        if not cerradas:
            return "No veo el navegador abierto."
        return Rich(f"Cerrando el navegador ({cerradas} ventana"
                    f"{'s' if cerradas > 1 else ''}).", speak="")
    # "youtube.com" también debe encajar con la pestaña "YouTube - Brave"
    corto = re.sub(r"\.(com|es|net|org|tv|io|app)$", "", objetivo).strip()
    # 1) pestañas del navegador, TAMBIÉN las de segundo plano (UIA)
    try:
        cerrada = _cerrar_pestana_uia(tuple({objetivo, corto}))
    except Exception:
        cerrada = None
    if cerrada:
        # la pestaña activa de Chromium se llama "Uso de memoria de X: N MB"
        cerrada = re.sub(r"^Uso de memoria de (.+): \d+ [MG]B$", r"\1", cerrada)
        visible = cerrada if len(cerrada) <= 60 else cerrada[:57] + "…"
        return Rich(f"Cerrando la pestaña «{visible}».", speak="")
    # 2) ventanas por título (apps normales; el navegador en pantalla
    # completa no expone pestañas y cae aquí)
    candidatas = []
    for hwnd, titulo in _ventanas_visibles():
        texto = titulo.lower()
        if "jarvis" in texto:  # no cerrarse a sí mismo
            continue
        if objetivo in texto or (corto and corto in texto):
            candidatas.append((100, hwnd, titulo))
        else:
            puntuacion = fuzz.partial_ratio(corto or objetivo, texto)
            if puntuacion >= 85:
                candidatas.append((puntuacion, hwnd, titulo))
    if not candidatas:
        return f"No veo ninguna ventana de «{ventana}»."
    candidatas.sort(key=lambda c: -c[0])
    _puntuacion, hwnd, titulo = candidatas[0]
    visible = titulo if len(titulo) <= 60 else titulo[:57] + "…"
    if _exe_de(hwnd) in NAVEGADORES:
        if _cerrar_pestana(hwnd):
            return Rich(f"Cerrando la pestaña «{visible}».", speak="")
        return (f"He visto «{visible}» pero no he podido cerrar solo esa "
                "pestaña. Di «cierra el navegador» si lo quieres cerrar entero.")
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    return Rich(f"Cerrando «{visible}».", speak="")


# -- pestañas en segundo plano (UI Automation) --------------------------------

def _pestanas_de(hwnd, uia, UIA) -> list:
    elemento = uia.ElementFromHandle(hwnd)
    cond = uia.CreatePropertyCondition(
        UIA.UIA_ControlTypePropertyId, UIA.UIA_TabItemControlTypeId
    )
    encontradas = elemento.FindAll(UIA.TreeScope_Descendants, cond)
    return [encontradas.GetElement(i) for i in range(encontradas.Length)]


def _seleccion(tab, UIA):
    return tab.GetCurrentPattern(
        UIA.UIA_SelectionItemPatternId
    ).QueryInterface(UIA.IUIAutomationSelectionItemPattern)


def _cerrar_pestana_uia(claves: tuple[str, ...]) -> str | None:
    """Busca en TODAS las pestañas de TODAS las ventanas del navegador
    (también las de segundo plano): selecciona la que case, pulsa su botón
    de cerrar y reactiva la pestaña que estaba antes. Devuelve el título
    cerrado, o None. El árbol de accesibilidad de Chromium es perezoso:
    puede tardar un intento en poblarse."""
    from jarvis.skills.whatsapp import _uia

    uia, UIA = _uia()
    cond_btn = uia.CreatePropertyCondition(
        UIA.UIA_ControlTypePropertyId, UIA.UIA_ButtonControlTypeId
    )
    for _intento in range(3):
        for hwnd, _titulo in _ventanas_visibles():
            if _exe_de(hwnd) not in NAVEGADORES:
                continue
            pestanas = _pestanas_de(hwnd, uia, UIA)
            activa_previa = next(
                (t.CurrentName for t in pestanas
                 if _seleccion(t, UIA).CurrentIsSelected), None
            )
            for tab in pestanas:
                nombre = tab.CurrentName or ""
                if not any(c and c in nombre.lower() for c in claves):
                    continue
                if not _seleccion(tab, UIA).CurrentIsSelected:
                    _seleccion(tab, UIA).Select()
                    time.sleep(0.4)
                # rebuscar: al seleccionar, el árbol cambia y aparece el botón
                for tab2 in _pestanas_de(hwnd, uia, UIA):
                    nombre2 = tab2.CurrentName or ""
                    if not any(c and c in nombre2.lower() for c in claves):
                        continue
                    boton = tab2.FindFirst(UIA.TreeScope_Children, cond_btn)
                    if boton is None:
                        continue
                    boton.GetCurrentPattern(
                        UIA.UIA_InvokePatternId
                    ).QueryInterface(UIA.IUIAutomationInvokePattern).Invoke()
                    time.sleep(0.3)
                    if activa_previa and nombre.lower() not in activa_previa.lower():
                        # devolver el primer plano a la pestaña que estaba
                        for tab3 in _pestanas_de(hwnd, uia, UIA):
                            n3 = tab3.CurrentName or ""
                            if n3 and (n3 == activa_previa or n3 in activa_previa):
                                _seleccion(tab3, UIA).Select()
                                break
                    return nombre
        time.sleep(0.6)
    return None
