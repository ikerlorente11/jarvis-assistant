"""«Envíalo» / «no lo envíes» — una sola orden para el usuario.

Aquí se decide a qué borrador se refiere: el WhatsApp escrito en pantalla
tiene prioridad (es lo último que ha quedado a la vista); si no, el correo
redactado. La confirmación es SIEMPRE humana (no_tool en el catálogo).
"""

from __future__ import annotations

from jarvis.skills import mail, whatsapp


def confirmar(config: dict):
    if whatsapp._pendiente is not None:
        return whatsapp.confirmar(config)
    return mail.confirmar(config)


def cancelar(config: dict):
    if whatsapp._pendiente is not None:
        return whatsapp.cancelar(config)
    return mail.cancelar(config)
