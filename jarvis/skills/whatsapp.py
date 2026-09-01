"""WhatsApp: abrir el chat con el mensaje ya escrito.

Enviar de verdad queda en manos del usuario: se deja el chat abierto con
el texto puesto y él pulsa enviar — la misma filosofía de confirmación
humana que el correo (el asistente nunca «envía» solo).

Dos caminos:
- Número (dictado o en `phones:` de config.yaml): URI whatsapp://send.
  Sin prefijo se asume España (+34).
- Nombre de contacto: WhatsApp ya no expone los números (IDs @lid), así
  que se maneja la propia app — es WhatsApp Web empaquetado y su teclado
  es fiable: buscador → nombre → Enter abre el chat → se escribe el
  mensaje (el cursor cae solo en la caja). Necesita la app en primer
  plano un par de segundos.
"""

from __future__ import annotations

import ctypes
import os
import re
import time
import unicodedata
from ctypes import wintypes
from urllib.parse import quote

user32 = ctypes.windll.user32

VK_RETURN = 0x0D
VK_MENU = 0x12  # Alt
VK_CONTROL = 0x11
VK_A = 0x41
VK_DELETE = 0x2E
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


_ULONG_PTR = ctypes.c_size_t  # 8 bytes en x64: el tamaño de INPUT debe ser
# exacto (la unión incluye MOUSEINPUT, el miembro más grande) o SendInput
# rechaza la llamada entera en silencio


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _enviar_entradas(entradas: list) -> bool:
    arr = (_INPUT * len(entradas))(*entradas)
    enviadas = user32.SendInput(len(entradas), arr, ctypes.sizeof(_INPUT))
    return enviadas == len(entradas)


def _teclear(texto: str) -> bool:
    """Escribe texto como entrada de teclado real (unicode, sin layout)."""
    entradas = []
    for caracter in texto:
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            item = _INPUT()
            item.type = 1  # INPUT_KEYBOARD
            item.ki = _KEYBDINPUT(0, ord(caracter), flags, 0, 0)
            entradas.append(item)
    return _enviar_entradas(entradas)


def _tecla(vk: int) -> bool:
    entradas = []
    for flags in (0, KEYEVENTF_KEYUP):
        item = _INPUT()
        item.type = 1
        item.ki = _KEYBDINPUT(vk, 0, flags, 0, 0)
        entradas.append(item)
    return _enviar_entradas(entradas)


def _borrar_todo() -> None:
    """Ctrl+A + Supr en el control con foco."""
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_A, 0, 0, 0)
    user32.keybd_event(VK_A, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    _tecla(VK_DELETE)


def _fold(texto: str) -> str:
    """minúsculas y sin tildes: el dictado llega normalizado («mama»)."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))

SEPARADORES = re.compile(
    r"\s+(?:diciendo(?:\s+que)?|que\s+diga|con\s+el\s+mensaje(?:\s+de)?|de\s+que)\s+",
    re.IGNORECASE,
)

# Mensaje escrito en el chat, a la espera del «envíalo» del usuario
_pendiente: dict | None = None


def enviar(config: dict, peticion: str):
    """peticion: «a 612345678 diciendo que llego tarde» / «a mamá que diga…»."""
    global _pendiente
    from jarvis.results import Rich

    if _pendiente is not None:
        # sin esto, un «sí» ambiguo que acabe en el LLM puede hacerle
        # llamar a esta tool otra vez y entrar en bucle de preguntas
        anterior = _pendiente["destino"]
        return Rich(
            f"Ya tienes un mensaje preparado para {anterior}: "
            "di «envíalo» o «no lo envíes».",
            speak=f"Ya hay uno preparado para {anterior}. "
                  "¿Lo envío o lo descarto?",
        )
    partes = SEPARADORES.split(peticion.strip(), maxsplit=1)
    if len(partes) == 2:
        destino, mensaje = partes[0].strip(), partes[1].strip()
    else:
        # sin «diciendo X» literal («…explicándole lo que estamos
        # haciendo»): el LLM redacta el mensaje
        redactado = _redactar_con_llm(config, peticion)
        if redactado is None:
            return ("Dímelo así: «envía un whatsapp a NÚMERO (o contacto) "
                    "diciendo MENSAJE» — o arranca Ollama para que pueda "
                    "redactarlo yo.")
        destino, mensaje = redactado
    destino = re.sub(r"^(?:a|al)\s+", "", destino, flags=re.IGNORECASE).strip()
    if not mensaje:
        return "¿Y el mensaje? «… diciendo MENSAJE»."
    agenda = {
        _fold(str(nombre)): str(numero)
        for nombre, numero in (config.get("phones") or {}).items()
    }
    telefono = agenda.get(_fold(destino))
    if telefono is None:
        digitos = re.sub(r"\D", "", destino)
        if len(digitos) < 9:
            # es un nombre: que lo resuelva el buscador de la propia app
            error = _abrir_chat_por_nombre(destino, mensaje)
            if error:
                return error
            return Rich(
                f"Chat con {destino} abierto y mensaje escrito: «{mensaje}». "
                "¿Lo envío?",
                speak=f"Mensaje para {destino} preparado. ¿Lo envío?",
            )
        telefono = digitos
    telefono = re.sub(r"\D", "", telefono)
    if len(telefono) == 9:  # sin prefijo de país → España
        telefono = "34" + telefono
    try:
        os.startfile(f"whatsapp://send?phone={telefono}&text={quote(mensaje)}")
    except OSError:
        return "No he podido abrir WhatsApp (¿está instalado?)."
    hwnd = _esperar_ventana(8)
    if hwnd is not None:
        _pendiente = {"hwnd": hwnd, "destino": destino}
    return Rich(
        f"WhatsApp abierto con el mensaje para {destino} preparado: "
        f"«{mensaje}». ¿Lo envío?",
        speak=f"Mensaje para {destino} preparado. ¿Lo envío?",
    )


def _redactar_con_llm(config: dict, peticion: str) -> tuple[str, str] | None:
    """«a mi principesa explicando X» → (destinatario, mensaje redactado).
    Usa el contexto reciente de la conversación para saber de qué habla."""
    brain = config.get("_brain")
    if brain is None or not getattr(brain, "enabled", False):
        return None
    historial = list(getattr(brain, "history", []))[-6:]
    contexto = "\n".join(
        f"{m.get('role', '')}: {str(m.get('content', ''))[:300]}"
        for m in historial
    ) or "(sin conversación previa)"
    respuesta = brain.quick(
        "El usuario quiere mandar un WhatsApp. Su petición: "
        f"«{peticion}»\n"
        "Contexto reciente de su conversación con el asistente:\n"
        f"{contexto}\n\n"
        "Responde EXACTAMENTE con dos líneas:\n"
        "PARA: el contacto o número, tal cual lo nombró el usuario\n"
        "MENSAJE: el mensaje redactado en primera persona del usuario, "
        "natural y breve, listo para enviarse tal cual",
        "",
    )
    if not respuesta:
        return None
    para = re.search(r"PARA:\s*(.+)", respuesta)
    mensaje = re.search(r"MENSAJE:\s*(.+)", respuesta, re.DOTALL)
    if not para or not mensaje:
        return None
    return (
        para.group(1).strip(),
        " ".join(mensaje.group(1).split()),
    )


# -- manejo de la app por nombre de contacto ---------------------------------

def _uia():
    """Cliente UI Automation (COM inicializado para este hilo)."""
    import comtypes

    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    import comtypes.client

    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as UIA

    cliente = comtypes.client.CreateObject(
        UIA.CUIAutomation, interface=UIA.IUIAutomation
    )
    return cliente, UIA


def _esperar_ventana(timeout_s: float):
    from jarvis.skills.screens import _exe_de, _ventanas_visibles

    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        for hwnd, _titulo in _ventanas_visibles():
            if "whatsapp" in _exe_de(hwnd):
                return hwnd
        time.sleep(0.4)
    return None


def _traer_al_frente(hwnd) -> bool:
    """Windows niega el primer plano a procesos en segundo plano; el toque
    de Alt (última entrada nuestra) desbloquea el permiso."""
    kernel32 = ctypes.windll.kernel32
    for _ in range(5):
        this_t = kernel32.GetCurrentThreadId()
        fore_t = user32.GetWindowThreadProcessId(
            user32.GetForegroundWindow(), None
        )
        targ_t = user32.GetWindowThreadProcessId(hwnd, None)
        _tecla(VK_MENU)  # el truco del Alt
        user32.AttachThreadInput(this_t, fore_t, True)
        user32.AttachThreadInput(this_t, targ_t, True)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(this_t, fore_t, False)
        user32.AttachThreadInput(this_t, targ_t, False)
        time.sleep(0.35)
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.4)
    return False


def _asegurar_frente(hwnd) -> bool:
    """Sigue (o vuelve a estar) en primer plano; se recupera si el usuario
    tocó algo a mitad."""
    if user32.GetForegroundWindow() == hwnd:
        return True
    return _traer_al_frente(hwnd)


def _abrir_chat_por_nombre(nombre: str, mensaje: str) -> str | None:
    """Abre WhatsApp, busca el contacto por nombre y deja el mensaje
    escrito SIN enviarlo. Devuelve un error legible, o None si todo bien."""
    try:
        os.startfile("whatsapp://")
    except OSError:
        return "No he podido abrir WhatsApp (¿está instalado?)."
    hwnd = _esperar_ventana(8)
    if hwnd is None:
        return "WhatsApp no ha llegado a abrirse."
    if not _traer_al_frente(hwnd):
        return ("No he podido poner WhatsApp en primer plano — si estabas "
                "usando el teclado, prueba otra vez sin tocarlo.")
    try:
        uia, UIA = _uia()
        raiz = uia.ElementFromHandle(hwnd)
        cond_edit = uia.CreatePropertyCondition(
            UIA.UIA_ControlTypePropertyId, UIA.UIA_EditControlTypeId
        )
        busqueda = raiz.FindFirst(UIA.TreeScope_Descendants, cond_edit)
        if busqueda is None:
            return "No encuentro el buscador de WhatsApp."
        # foco de teclado en el buscador — verificado de verdad (el value
        # pattern del WebView no es fiable para leer lo escrito)
        enfocado = False
        for _intento in range(3):
            busqueda.SetFocus()
            time.sleep(0.35)
            if busqueda.CurrentHasKeyboardFocus:
                enfocado = True
                break
        if not enfocado:
            return "No he podido poner el cursor en el buscador de WhatsApp."
        if not _asegurar_frente(hwnd):  # jamás teclear a ciegas
            return ("No consigo mantener WhatsApp en primer plano — prueba "
                    "otra vez sin tocar el teclado ni el ratón unos segundos.")
        _borrar_todo()
        _teclear(nombre)
        time.sleep(1.1)  # que salgan los resultados
        _tecla(VK_RETURN)  # abre el primer chat que encaje
        time.sleep(1.3)
        caja = _caja_mensaje(hwnd)
        if caja is None:
            if busqueda.CurrentHasKeyboardFocus:
                _borrar_todo()  # dejar el buscador limpio
            return f"No veo ningún chat de «{nombre}» en WhatsApp."
        if not caja.CurrentHasKeyboardFocus:
            caja.SetFocus()
            time.sleep(0.3)
        if not _asegurar_frente(hwnd):
            return ("He abierto el chat pero perdí el primer plano antes de "
                    "escribir; el mensaje era: «" + mensaje + "».")
        _borrar_todo()  # por si el chat tenía un borrador antiguo
        _teclear(mensaje)
        global _pendiente
        _pendiente = {"hwnd": hwnd, "destino": nombre}
        return None
    except Exception as exc:
        return f"No he podido manejar WhatsApp: {exc.__class__.__name__}."


def _caja_mensaje(hwnd):
    """El cuadro «Escribir un mensaje para X» del chat abierto, o None."""
    uia, UIA = _uia()
    raiz = uia.ElementFromHandle(hwnd)  # árbol fresco: la UI cambia
    cond = uia.CreatePropertyCondition(
        UIA.UIA_ControlTypePropertyId, UIA.UIA_EditControlTypeId
    )
    edits = raiz.FindAll(UIA.TreeScope_Descendants, cond)
    for i in range(edits.Length):
        elemento = edits.GetElement(i)
        if "escribir un mensaje" in (elemento.CurrentName or "").lower():
            return elemento
    return None


def _pulsar_enviar(hwnd) -> bool:
    """Pulsa el botón «Enviar» del chat vía UIA (Invoke): no necesita foco
    ni primer plano. False si el botón no está (caja vacía) o falla."""
    try:
        uia, UIA = _uia()
        raiz = uia.ElementFromHandle(hwnd)
        cond = uia.CreatePropertyCondition(
            UIA.UIA_ControlTypePropertyId, UIA.UIA_ButtonControlTypeId
        )
        botones = raiz.FindAll(UIA.TreeScope_Descendants, cond)
        for i in range(botones.Length):
            try:
                boton = botones.GetElement(i)
                if (boton.CurrentName or "").strip().lower() == "enviar":
                    boton.GetCurrentPattern(
                        UIA.UIA_InvokePatternId
                    ).QueryInterface(UIA.IUIAutomationInvokePattern).Invoke()
                    return True
            except Exception:
                continue  # elementos volátiles: el árbol cambia bajo los pies
    except Exception:
        pass
    return False


def confirmar(config: dict):
    """«Envíalo»: pulsa el botón Enviar del mensaje que quedó escrito."""
    global _pendiente
    from jarvis.results import Rich

    if _pendiente is None:
        return "No hay ningún whatsapp pendiente."
    hwnd, destino = _pendiente["hwnd"], _pendiente["destino"]
    if not user32.IsWindow(hwnd):
        _pendiente = None
        return "La ventana de WhatsApp ya no está; vuelve a dictarme el mensaje."
    # 1) botón Enviar por UIA: sin foco ni primer plano
    if _pulsar_enviar(hwnd):
        _pendiente = None
        return Rich(f"Enviado a {destino}. ✔", speak=f"Enviado a {destino}.")
    # 2) plan B: al frente + Enter en la caja
    anterior = user32.GetForegroundWindow()
    if not _traer_al_frente(hwnd):
        return "No he podido poner WhatsApp en primer plano; repite «envíalo»."
    caja = _caja_mensaje(hwnd)
    if caja is None:
        _pendiente = None
        return "El chat ya no está abierto; vuelve a dictarme el mensaje."
    caja.SetFocus()
    time.sleep(0.3)
    if user32.GetForegroundWindow() != hwnd:
        return "No he podido pulsar enviar; hazlo tú o repite «envíalo»."
    _tecla(VK_RETURN)
    _pendiente = None
    if anterior and anterior != hwnd:
        time.sleep(0.2)
        _traer_al_frente(anterior)  # de vuelta a lo tuyo
    return Rich(f"Enviado a {destino}. ✔", speak=f"Enviado a {destino}.")


def cancelar(config: dict):
    """«No lo envíes»: borra lo escrito y olvida el pendiente."""
    global _pendiente
    from jarvis.results import Rich

    if _pendiente is None:
        return "No hay ningún whatsapp pendiente."
    hwnd, destino = _pendiente["hwnd"], _pendiente["destino"]
    anterior = user32.GetForegroundWindow()
    _pendiente = None
    if user32.IsWindow(hwnd) and _traer_al_frente(hwnd):
        caja = _caja_mensaje(hwnd)
        if caja is not None:
            caja.SetFocus()
            time.sleep(0.25)
            if caja.CurrentHasKeyboardFocus:
                _borrar_todo()
                if anterior and anterior != hwnd:
                    time.sleep(0.2)
                    _traer_al_frente(anterior)
                return Rich(f"Descartado el mensaje a {destino}.",
                            speak="Descartado.")
    return (f"Olvidado el mensaje a {destino} (no he podido borrar lo "
            "escrito en el chat; bórralo tú).")
