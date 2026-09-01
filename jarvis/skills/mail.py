"""Correo: enlazado de cuenta (IMAP) y lectura de correos nuevos.

La contraseña (de aplicación) va al Almacén de credenciales de Windows vía
keyring — nunca a un fichero. La dirección y los servidores, a
config.local.yaml. Se puede enlazar otra cuenta cuando se quiera desde
⚙ Ajustes. El envío con redacción del LLM llega en la siguiente iteración.
"""

from __future__ import annotations

import imaplib
from email.header import decode_header

import keyring

from jarvis import config as config_module

SERVICE = "jarvis-mail"

IMAP_PRESETS = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com",
    "outlook.es": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "hotmail.es": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com",
}


def enlazar(address: str, password: str, imap_server: str = "") -> str:
    """Prueba las credenciales y, si funcionan, las guarda. → mensaje."""
    address = address.strip().lower()
    if "@" not in address:
        return "Esa dirección no parece un correo."
    dominio = address.split("@", 1)[1]
    servidor = imap_server.strip() or IMAP_PRESETS.get(dominio, f"imap.{dominio}")
    try:
        with imaplib.IMAP4_SSL(servidor, timeout=10) as imap:
            imap.login(address, password)
    except imaplib.IMAP4.error:
        return ("No he podido iniciar sesión. Para Gmail/Outlook necesitas una "
                "«contraseña de aplicación», no la normal.")
    except OSError:
        return f"No llego al servidor {servidor}."
    keyring.set_password(SERVICE, address, password)
    config_module.save_local({"mail": {"address": address, "imap": servidor}})
    return f"Correo enlazado: {address}."


def desenlazar() -> str:
    cuenta = (config_module.load().get("mail") or {}).get("address")
    if cuenta:
        try:
            keyring.delete_password(SERVICE, cuenta)
        except keyring.errors.PasswordDeleteError:
            pass
    config_module.save_local({"mail": {"address": "", "imap": ""}})
    return "Correo desenlazado."


def cuenta_enlazada(config: dict) -> str | None:
    return (config.get("mail") or {}).get("address") or None


def leer(config: dict):
    from jarvis.results import Rich

    cuenta = cuenta_enlazada(config)
    if not cuenta:
        return "No hay ningún correo enlazado — hazlo desde ⚙ Ajustes."
    password = keyring.get_password(SERVICE, cuenta)
    servidor = config["mail"].get("imap") or "imap." + cuenta.split("@", 1)[1]
    if not password:
        return "No encuentro la contraseña guardada; vuelve a enlazar el correo."
    try:
        with imaplib.IMAP4_SSL(servidor, timeout=10) as imap:
            imap.login(cuenta, password)
            imap.select("INBOX", readonly=True)
            _estado, datos = imap.search(None, "UNSEEN")
            ids = datos[0].split()
            if not ids:
                return Rich("No tienes correos nuevos.",
                            speak="No tienes correos nuevos.")
            lineas = []
            for msg_id in ids[-5:][::-1]:  # los 5 más recientes
                _estado, cabecera = imap.fetch(
                    msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])"
                )
                remitente, asunto = _parse_cabecera(cabecera)
                lineas.append(f"• {asunto}  — {remitente}")
    except (imaplib.IMAP4.error, OSError) as exc:
        return f"No he podido leer el correo: {exc.__class__.__name__}."

    total = len(ids)
    plural = "s" if total != 1 else ""
    texto = f"Tienes {total} correo{plural} sin leer:\n" + "\n".join(lineas)
    return Rich(texto, speak=f"Tienes {total} correo{plural} sin leer.")


def _parse_cabecera(cabecera) -> tuple[str, str]:
    import email as email_lib

    for parte in cabecera:
        if isinstance(parte, tuple):
            mensaje = email_lib.message_from_bytes(parte[1])
            return (_decodificar(mensaje.get("From", "?")),
                    _decodificar(mensaje.get("Subject", "(sin asunto)")))
    return "?", "(sin asunto)"


def _decodificar(valor: str) -> str:
    partes = []
    for texto, charset in decode_header(valor):
        if isinstance(texto, bytes):
            texto = texto.decode(charset or "utf-8", errors="replace")
        partes.append(texto)
    junto = "".join(partes)
    # "Nombre <correo@x>" → Nombre
    return junto.split("<")[0].strip().strip('"') or junto
