"""Correo: enlazado de cuenta (IMAP) y lectura de correos nuevos.

La contraseña (de aplicación) va al Almacén de credenciales de Windows vía
keyring — nunca a un fichero. La dirección y los servidores, a
config.local.yaml. Se puede enlazar otra cuenta cuando se quiera desde
⚙ Ajustes. El envío con redacción del LLM llega en la siguiente iteración.
"""

from __future__ import annotations

import imaplib
from email.header import decode_header
from pathlib import Path

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

SMTP_PRESETS = {
    "gmail.com": "smtp.gmail.com",
    "googlemail.com": "smtp.gmail.com",
    "outlook.com": "smtp-mail.outlook.com",
    "outlook.es": "smtp-mail.outlook.com",
    "hotmail.com": "smtp-mail.outlook.com",
    "hotmail.es": "smtp-mail.outlook.com",
    "live.com": "smtp-mail.outlook.com",
    "yahoo.com": "smtp.mail.yahoo.com",
}

_borrador: dict | None = None  # borrador pendiente de confirmar


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


def _sesion(config: dict):
    """→ (imap con INBOX seleccionada, None) o (None, mensaje de error)."""
    cuenta = cuenta_enlazada(config)
    if not cuenta:
        return None, "No hay ningún correo enlazado — hazlo desde ⚙ Ajustes."
    password = keyring.get_password(SERVICE, cuenta)
    if not password:
        return None, "No encuentro la contraseña guardada; vuelve a enlazar el correo."
    servidor = config["mail"].get("imap") or "imap." + cuenta.split("@", 1)[1]
    try:
        imap = imaplib.IMAP4_SSL(servidor, timeout=10)
        imap.login(cuenta, password)
        imap.select("INBOX", readonly=True)
        return imap, None
    except (imaplib.IMAP4.error, OSError) as exc:
        return None, f"No he podido conectar con el correo: {exc.__class__.__name__}."


def de_remitente(config: dict, remitente: str):
    """Busca correos de un remitente (nombre o dirección) y lista los últimos."""
    from email.utils import parsedate_to_datetime

    from jarvis.results import Rich

    termino = remitente.strip()
    try:
        termino.encode("ascii")
    except UnicodeEncodeError:
        return ("La búsqueda IMAP no admite tildes: prueba con la dirección "
                "o el nombre sin acentos.")
    imap, error = _sesion(config)
    if error:
        return error
    try:
        _estado, datos = imap.search(None, f'(FROM "{termino}")')
        ids = datos[0].split()
        if not ids:
            return f"No encuentro ningún correo de «{remitente}»."
        _estado, sin_leer_datos = imap.search(None, f'(UNSEEN FROM "{termino}")')
        sin_leer = set(sin_leer_datos[0].split())
        lineas = []
        for msg_id in ids[-5:][::-1]:
            _estado, cabecera = imap.fetch(
                msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
            )
            quien, asunto = _parse_cabecera(cabecera)
            fecha = ""
            for parte in cabecera:
                if isinstance(parte, tuple):
                    import email as email_lib

                    crudo = email_lib.message_from_bytes(parte[1]).get("Date")
                    if crudo:
                        try:
                            fecha = f"{parsedate_to_datetime(crudo):%d/%m} · "
                        except (TypeError, ValueError):
                            pass
            marca = "🔵 " if msg_id in sin_leer else ""
            lineas.append(f"• {marca}{fecha}{asunto}")
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    total, nuevos = len(ids), len(sin_leer)
    resumen_nuevos = f", {nuevos} sin leer" if nuevos else ""
    texto = (f"{total} correo{'s' if total != 1 else ''} de «{remitente}»"
             f"{resumen_nuevos}. Los últimos:\n" + "\n".join(lineas))
    hablado = (f"Tienes {total} correo{'s' if total != 1 else ''} de {remitente}"
               f"{resumen_nuevos}. El más reciente: "
               + lineas[0].split("· ")[-1].removeprefix("• "))
    return Rich(texto, speak=hablado)


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


def ultimo(config: dict):
    """Lee el último correo recibido y lo resume con el LLM: de qué trata
    y si requiere hacer algo — no solo remitente y asunto."""
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
            _estado, datos = imap.search(None, "ALL")
            ids = datos[0].split()
            if not ids:
                return "Tu bandeja de entrada está vacía."
            _estado, crudo = imap.fetch(ids[-1], "(BODY.PEEK[])")
    except (imaplib.IMAP4.error, OSError) as exc:
        return f"No he podido leer el correo: {exc.__class__.__name__}."

    import email as email_lib

    mensaje = None
    for parte in crudo:
        if isinstance(parte, tuple):
            mensaje = email_lib.message_from_bytes(parte[1])
            break
    if mensaje is None:
        return "No he podido descargar el correo."
    remitente = _decodificar(mensaje.get("From", "?"))
    asunto = _decodificar(mensaje.get("Subject", "(sin asunto)"))
    cuerpo = _cuerpo(mensaje)[:4000]

    brain = config.get("_brain")
    if brain is not None and cuerpo.strip():
        resumen = brain.quick(
            "Resume este correo en 2 o 3 frases: de qué trata y, si pide "
            "hacer algo, qué y para cuándo. Solo lo relevante para quien "
            "lo recibe.",
            f"De: {remitente}\nAsunto: {asunto}\n\n{cuerpo}",
        )
        if resumen:
            texto = f"📩 {asunto} — {remitente}\n\n{resumen}"
            return Rich(texto, speak=f"Último correo, de {remitente}. {resumen}")

    # sin LLM: al menos el principio del cuerpo, no solo el asunto
    extracto = " ".join(cuerpo.split())[:350]
    return Rich(
        f"📩 {asunto} — {remitente}\n\n{extracto}…",
        speak=f"Último correo de {remitente}: {asunto}.",
    )


def redactar(config: dict, peticion: str, para_mi: str = ""):
    """El LLM redacta un borrador a partir de la petición; NUNCA se envía
    sin que el usuario lo revise y confirme."""
    import re

    from jarvis.results import Item, Rich

    global _borrador
    cuenta = cuenta_enlazada(config)
    if not cuenta:
        return "No hay ningún correo enlazado — hazlo desde ⚙ Ajustes."

    # destinatario: "a mí mismo"/"envíame" → la cuenta enlazada;
    # si no, dirección literal en la petición o alias de contacts
    para = None
    if para_mi or re.search(
        r"\b(a mi mism[oa]|mi mism[oa]|para mi|a mi correo|mi correo|"
        r"mi direccion|mi dirección)\b", peticion, re.IGNORECASE
    ):
        para = cuenta
    if para is None:
        match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", peticion)
        para = match.group(0) if match else None
    if para is None:
        contactos = config.get("contacts") or {}
        for nombre, direccion in contactos.items():
            if nombre.lower() in peticion.lower():
                para = direccion
                break
    if para is None:
        return ("No sé la dirección del destinatario: di «a mí mismo», una "
                "dirección («…a nombre@dominio.com») o un contacto guardado "
                "(«añade el contacto Nombre -> correo»).")

    # adjuntos: "…con el archivo informe adjunto" → se busca con Everything
    adjuntos = []
    encaje = re.search(
        r"(?:adjunta(?:ndo)?|con el (?:archivo|fichero)|el (?:archivo|fichero))"
        r"\s+([\w\-.]+)", peticion, re.IGNORECASE,
    )
    if encaje:
        nombre = encaje.group(1)
        ruta = _buscar_adjunto(config, nombre)
        if ruta is None:
            return f"No encuentro ningún archivo «{nombre}» para adjuntar."
        adjuntos.append(ruta)

    quiere_html = bool(re.search(
        r"\b(bonito|html|con estilo|currado|elegante|formateado|vistoso)\b",
        peticion, re.IGNORECASE,
    ))

    # "meme" = imagen de verdad, no texto: se descarga una y se incrusta
    meme = None
    if re.search(r"\bmemes?\b", peticion, re.IGNORECASE):
        meme = _obtener_meme()
        if meme is None:
            return "No he podido conseguir un meme de internet ahora mismo."
        quiere_html = True  # con imagen, el correo va en HTML

    brain = config.get("_brain")
    if brain is None:
        return "Para redactar necesito el LLM y no está disponible."
    nota_meme = (
        f"\nDebajo del texto irá una imagen de meme titulada "
        f"«{meme['titulo']}» que añadiré yo: escribe SOLO una frase breve de "
        f"acompañamiento. NO escribas etiquetas <img>." if meme else ""
    )
    if quiere_html:
        salida = brain.quick(
            "Redacta un correo HTML vistoso a partir de la petición. Responde "
            "EXACTAMENTE en este formato, sin nada más:\n"
            "ASUNTO: <una línea>\nCUERPO_HTML:\n<un único <div> con estilos "
            "inline (style=\"...\"), colores suaves y buena tipografía. "
            "Sin <html>, <head>, <script> ni markdown>" + nota_meme,
            f"Petición: {peticion}",
        )
    else:
        salida = brain.quick(
            "Redacta un correo en español a partir de la petición. Responde "
            "EXACTAMENTE en este formato, sin nada más:\n"
            "ASUNTO: <una línea>\nCUERPO:\n<cuerpo breve y natural>",
            f"Petición: {peticion}",
        )
    if not salida:
        return "No he podido redactar el borrador (¿Ollama está en marcha?)."
    salida = re.sub(r"```\w*|```", "", salida).strip()  # sin vallas de código
    asunto, cuerpo, cuerpo_html = "Mensaje", salida, None
    encaje = re.search(r"ASUNTO:\s*(.+?)\s*CUERPO(_HTML)?:\s*(.+)", salida, re.DOTALL)
    if encaje:
        asunto = encaje.group(1).strip()
        contenido = encaje.group(3).strip()
        if encaje.group(2) or quiere_html:
            cuerpo_html = re.sub(r"<script.*?</script>", "", contenido,
                                 flags=re.DOTALL | re.IGNORECASE)
            # cualquier <img> del LLM es inventada (URLs rotas): fuera;
            # las imágenes reales las añadimos nosotros con cid
            cuerpo_html = re.sub(r"<img[^>]*>", "", cuerpo_html,
                                 flags=re.IGNORECASE)
            cuerpo = _texto_plano(cuerpo_html)
        else:
            cuerpo = contenido

    inline = None
    if meme and cuerpo_html:
        inline = meme["ruta"]
        cuerpo_html += (
            "<div style='text-align:center;margin-top:10px'>"
            "<img src='cid:meme' style='max-width:100%;border-radius:8px'></div>"
        )
    _borrador = {"para": para, "asunto": asunto, "cuerpo": cuerpo,
                 "html": cuerpo_html, "adjuntos": adjuntos, "inline": inline}
    botones = [
        Item("intent", "✅  Enviarlo", "correo_confirmar"),
        Item("intent", "❌  Descartarlo", "correo_cancelar"),
    ]
    linea_adjuntos = "".join(f"\n📎 {Path(r).name}" for r in adjuntos)
    if cuerpo_html:
        # vista previa sobre fondo blanco: los correos HTML se diseñan para
        # fondo claro y sobre la tarjeta oscura no se leían bien
        vista = cuerpo_html
        if inline:
            vista = vista.replace("cid:meme", Path(inline).as_uri())
        cabecera = (f"<div style='font-size:12px;color:#8fa3c4'>Para: {para} · "
                    f"Asunto: {asunto}"
                    + "".join(f" · 📎 {Path(r).name}" for r in adjuntos)
                    + "</div>")
        preview = (cabecera + "<div style='background:#ffffff;color:#1a2233;"
                   f"padding:12px;border-radius:10px'>{vista}</div>")
        return Rich(
            f"Para: {para}\nAsunto: {asunto}{linea_adjuntos}\n{'─' * 30}\n{cuerpo}",
            items=botones,
            html=preview,
            speak="Te he preparado el borrador; revísalo y confirma.",
        )
    return Rich(
        f"Para: {para}\nAsunto: {asunto}{linea_adjuntos}\n{'─' * 30}\n{cuerpo}",
        items=botones,
        speak="Te he preparado el borrador; revísalo y confirma.",
    )


def _obtener_meme() -> dict | None:
    """Meme aleatorio (meme-api.com, gratis y sin clave) → imagen local."""
    import tempfile

    import requests

    try:
        datos = requests.get("https://meme-api.com/gimme", timeout=8).json()
        url = datos.get("url", "")
        imagen = requests.get(url, timeout=10).content
        extension = url.rsplit(".", 1)[-1].lower()
        if extension not in ("jpg", "jpeg", "png", "gif", "webp"):
            extension = "jpg"
        ruta = Path(tempfile.gettempdir()) / f"jarvis-meme.{extension}"
        ruta.write_bytes(imagen)
        return {"titulo": datos.get("title", "Meme"), "ruta": str(ruta)}
    except (requests.RequestException, ValueError, OSError):
        return None


def _buscar_adjunto(config: dict, nombre: str) -> str | None:
    from rapidfuzz import fuzz

    from jarvis.skills.files import everything

    rutas = everything(config, f"file: {nombre}", max_results=20)
    if not rutas:
        return None
    return max(rutas, key=lambda r: fuzz.WRatio(nombre.lower(), Path(r).name.lower()))


def _texto_plano(html: str) -> str:
    import html as html_lib
    import re

    texto = re.sub(r"<br\s*/?>|</p>|</div>", "\n", html, flags=re.IGNORECASE)
    texto = re.sub(r"<[^>]+>", "", texto)
    return html_lib.unescape(re.sub(r"\n{3,}", "\n\n", texto)).strip()


def confirmar(config: dict) -> str:
    """Envía el borrador pendiente por SMTP (texto, HTML y adjuntos)."""
    import mimetypes
    import smtplib
    from email.message import EmailMessage

    global _borrador
    if _borrador is None:
        return "No hay ningún borrador pendiente."
    cuenta = cuenta_enlazada(config)
    password = keyring.get_password(SERVICE, cuenta) if cuenta else None
    if not cuenta or not password:
        return "No hay correo enlazado o falta la contraseña (⚙ Ajustes)."
    dominio = cuenta.split("@", 1)[1]
    servidor = SMTP_PRESETS.get(dominio, f"smtp.{dominio}")

    mensaje = EmailMessage()
    mensaje["From"] = cuenta
    mensaje["To"] = _borrador["para"]
    mensaje["Subject"] = _borrador["asunto"]
    mensaje.set_content(_borrador["cuerpo"])
    if _borrador.get("html"):
        mensaje.add_alternative(_borrador["html"], subtype="html")
        inline = _borrador.get("inline")
        if inline:
            try:
                datos = Path(inline).read_bytes()
            except OSError:
                return "No he podido leer la imagen del correo."
            extension = Path(inline).suffix.lstrip(".") or "jpeg"
            mensaje.get_payload()[-1].add_related(
                datos, maintype="image",
                subtype="jpeg" if extension == "jpg" else extension,
                cid="<meme>",
            )
    for ruta in _borrador.get("adjuntos", []):
        try:
            datos = Path(ruta).read_bytes()
        except OSError:
            return f"No he podido leer el adjunto {Path(ruta).name}."
        tipo, _codificacion = mimetypes.guess_type(ruta)
        maintype, subtype = (tipo or "application/octet-stream").split("/", 1)
        mensaje.add_attachment(
            datos, maintype=maintype, subtype=subtype, filename=Path(ruta).name
        )
    try:
        with smtplib.SMTP(servidor, 587, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(cuenta, password)
            smtp.send_message(mensaje)
    except (smtplib.SMTPException, OSError) as exc:
        return f"No he podido enviarlo: {exc.__class__.__name__}."
    from jarvis.results import Rich

    enviado_a = _borrador["para"]
    _borrador = None
    # confirmación sobria y sin voz: el usuario acaba de pulsar el botón
    return Rich(f"✉️ Enviado a {enviado_a}.", speak="")


def cancelar(config: dict) -> str:
    global _borrador
    if _borrador is None:
        return "No había ningún borrador pendiente."
    _borrador = None
    return "Borrador descartado."


def _cuerpo(mensaje) -> str:
    """Texto plano del correo; si solo hay HTML, se limpia de etiquetas."""
    import html as html_lib
    import re

    def _decodifica_parte(parte) -> str:
        payload = parte.get_payload(decode=True) or b""
        charset = parte.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    plano, html = "", ""
    partes = mensaje.walk() if mensaje.is_multipart() else [mensaje]
    for parte in partes:
        tipo = parte.get_content_type()
        if "attachment" in str(parte.get("Content-Disposition", "")):
            continue
        if tipo == "text/plain" and not plano:
            plano = _decodifica_parte(parte)
        elif tipo == "text/html" and not html:
            html = _decodifica_parte(parte)
    if plano.strip():
        return plano
    texto = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                   flags=re.DOTALL | re.IGNORECASE)
    texto = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", html_lib.unescape(texto)).strip()


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
