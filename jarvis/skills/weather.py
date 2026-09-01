"""Tiempo con Open-Meteo: API gratuita sin clave (geocoding + forecast).

La ciudad sale de config.yaml (`city:`); con `auto` (o vacío) se usa la
ubicación real de Windows (WiFi, precisa) y, si está desactivada, la IP
(aproximada). Siempre se puede pedir otra: "qué tiempo hace en X".
"""

from __future__ import annotations

from datetime import datetime

import requests

WMO = {
    0: "cielo despejado", 1: "mayormente despejado", 2: "parcialmente nublado",
    3: "nublado", 45: "niebla", 48: "niebla con escarcha",
    51: "llovizna débil", 53: "llovizna", 55: "llovizna intensa",
    61: "lluvia débil", 63: "lluvia", 65: "lluvia fuerte",
    66: "lluvia helada", 67: "lluvia helada fuerte",
    71: "nieve débil", 73: "nieve", 75: "nieve fuerte", 77: "cinarra",
    80: "chubascos débiles", 81: "chubascos", 82: "chubascos fuertes",
    85: "chubascos de nieve", 86: "chubascos de nieve fuertes",
    95: "tormenta", 96: "tormenta con granizo", 99: "tormenta con granizo fuerte",
}

DIAS_SEMANA = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
DIAS_LARGOS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

EMOJI = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️", 45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌧️", 61: "🌧️", 63: "🌧️", 65: "🌧️",
    66: "🌧️", 67: "🌧️", 71: "🌨️", 73: "🌨️", 75: "🌨️", 77: "🌨️",
    80: "🌦️", 81: "🌧️", 82: "⛈️", 85: "🌨️", 86: "🌨️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}

_ubicacion_auto: dict | None = None  # caché de la detección (una por sesión)


def hoy(config: dict, ciudad: str | None = None) -> str:
    sitio = _geolocalizar(config, ciudad)
    if isinstance(sitio, str):
        return sitio
    try:
        datos = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": sitio["latitude"],
                "longitude": sitio["longitude"],
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min",
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=6,
        ).json()
    except requests.RequestException as exc:
        return f"No he podido consultar el tiempo: {exc.__class__.__name__}."

    from jarvis.results import Rich

    actual = datos["current"]
    diario = datos["daily"]
    codigo = actual["weather_code"]
    cielo = WMO.get(codigo, "")
    temp = round(actual["temperature_2m"])
    maxima = round(diario["temperature_2m_max"][0])
    minima = round(diario["temperature_2m_min"][0])
    viento = round(actual["wind_speed_10m"])

    texto = (
        f"En {sitio['name']}: {temp}°C"
        + (f", {cielo}" if cielo else "")
        + f". Máxima {maxima}°, mínima {minima}°. Viento {viento} km/h."
    )
    hablado = (
        f"En {sitio['name']}, {temp} grados"
        + (f" y {cielo}" if cielo else "")
        + f". Máxima {maxima}, mínima {minima}. "
        f"Viento de {viento} kilómetros por hora."
    )
    html = f"""
    <table cellspacing="0" cellpadding="2"><tr>
      <td style="font-size:30px;padding-right:10px">{EMOJI.get(codigo, "🌡️")}</td>
      <td>
        <span style="font-size:28px;color:#f0f4fb;font-weight:bold">{temp}°</span>
        <span style="font-size:13px;color:#8fa3c4">&nbsp;{cielo.capitalize()}</span><br>
        <span style="font-size:12px;color:#c3cddd">{sitio['name']}
        &nbsp;·&nbsp; ↑&nbsp;{maxima}° &nbsp;↓&nbsp;{minima}°
        &nbsp;·&nbsp; 💨 {viento} km/h</span>
      </td>
    </tr></table>"""
    return Rich(texto, html=html, speak=hablado)


def prevision(config: dict, dias: str = "7", ciudad: str | None = None) -> str:
    try:
        n = max(1, min(14, int(dias.strip().split()[0])))
    except (ValueError, IndexError):
        return f"«{dias}» no es un número de días (1-14)."
    sitio = _geolocalizar(config, ciudad)
    if isinstance(sitio, str):
        return sitio
    try:
        datos = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": sitio["latitude"],
                "longitude": sitio["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,"
                "precipitation_probability_max",
                "forecast_days": n,
                "timezone": "auto",
            },
            timeout=6,
        ).json()
    except requests.RequestException as exc:
        return f"No he podido consultar el tiempo: {exc.__class__.__name__}."

    from jarvis.results import Rich

    diario = datos["daily"]
    lineas = []
    celdas = []
    minimas, maximas, dias_lluvia = [], [], []
    lluvias = diario.get("precipitation_probability_max")
    for i, fecha in enumerate(diario["time"]):
        dt = datetime.strptime(fecha, "%Y-%m-%d")
        codigo = diario["weather_code"][i]
        cielo = WMO.get(codigo, "")
        minima = round(diario["temperature_2m_min"][i])
        maxima = round(diario["temperature_2m_max"][i])
        minimas.append(minima)
        maximas.append(maxima)
        prob = lluvias[i] if lluvias and lluvias[i] is not None else 0
        if prob >= 40:
            dias_lluvia.append(DIAS_LARGOS[dt.weekday()])
        prob_txt = f", lluvia {prob}%" if prob else ""
        lineas.append(
            f"{DIAS_SEMANA[dt.weekday()]} {dt.day}: {minima}-{maxima}°, {cielo}{prob_txt}"
        )
        gota = (f"<br><span style='font-size:10px;color:#6fa8ff'>💧{prob}%</span>"
                if prob >= 20 else "")
        celdas.append(
            f"<td align='center' style='padding:4px 7px'>"
            f"<span style='font-size:11px;color:#8fa3c4'>{DIAS_SEMANA[dt.weekday()]} {dt.day}</span><br>"
            f"<span style='font-size:20px'>{EMOJI.get(codigo, '🌡️')}</span><br>"
            f"<span style='font-size:11px;color:#f0f4fb'><b>{maxima}°</b></span>"
            f"<span style='font-size:11px;color:#8fa3c4'> {minima}°</span>"
            f"{gota}</td>"
        )

    # tarjeta: cabecera + filas de hasta 7 días
    filas = "".join(
        "<tr>" + "".join(celdas[i:i + 7]) + "</tr>" for i in range(0, len(celdas), 7)
    )
    html = (
        f"<span style='font-size:13px;color:#c3cddd'>Previsión en "
        f"<b>{sitio['name']}</b></span>"
        f"<table cellspacing='0' cellpadding='0'>{filas}</table>"
    )

    # la voz resume, no lee la tabla entera
    resumen = (
        f"Previsión de {len(celdas)} días en {sitio['name']}: mínimas de "
        f"{min(minimas)}, máximas de hasta {max(maximas)} grados. "
    )
    if not dias_lluvia:
        resumen += "Sin lluvia a la vista."
    elif len(dias_lluvia) <= 3:
        resumen += "Lluvia probable el " + " y el ".join(dict.fromkeys(dias_lluvia)) + "."
    else:
        resumen += f"Lluvia probable en {len(dias_lluvia)} de los días."

    texto = f"Previsión en {sitio['name']}:\n" + "\n".join(lineas)
    return Rich(texto, html=html, speak=resumen)


def ubicacion(config: dict) -> str:
    """¿Dónde estamos? — la ubicación real, nunca inventada: GPS de Windows
    con nombre completo; si está denegado, ciudad aproximada por IP."""
    fijada = (config.get("city") or "auto").strip()
    if fijada.lower() != "auto":
        return f"Estamos en {fijada} (ciudad fijada en config.yaml)."
    coords = _windows_location()
    if coords:
        lat, lon = coords
        detalle = _lugar_detallado(lat, lon)
        if detalle:
            return f"Estamos en {detalle}."
        return (f"Estamos en {lat:.4f}, {lon:.4f} "
                "(no he podido ponerle nombre al sitio).")
    auto = _detectar_ubicacion()
    if auto:
        return f"Estamos en {auto['name']} (aproximado, por IP)."
    return ("No he podido detectar la ubicación: activa la ubicación de "
            "Windows o pon `city: TuCiudad` en config.yaml.")


def _lugar_detallado(lat: float, lon: float) -> str | None:
    """«Ciudad, provincia, país» con geocoding inverso gratuito."""
    try:
        datos = requests.get(
            "https://api.bigdatacloud.net/data/reverse-geocode-client",
            params={"latitude": lat, "longitude": lon, "localityLanguage": "es"},
            timeout=6,
        ).json()
    except (requests.RequestException, ValueError):
        return None
    partes = [
        datos.get("city") or datos.get("locality"),
        datos.get("principalSubdivision"),
        datos.get("countryName"),
    ]
    unicas = list(dict.fromkeys(p for p in partes if p))
    return ", ".join(unicas) if unicas else None


def _geolocalizar(config: dict, ciudad: str | None) -> dict | str:
    """→ dict con name/latitude/longitude; str = mensaje de error."""
    lugar = (ciudad or config.get("city") or "auto").strip()
    if lugar.lower() == "auto":
        auto = _detectar_ubicacion()
        if auto is None:
            return ("No he podido detectar tu ubicación (activa la ubicación "
                    "de Windows o pon `city: TuCiudad` en config.yaml).")
        return auto
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": lugar, "count": 1, "language": "es"},
            timeout=6,
        ).json()
    except requests.RequestException as exc:
        return f"No he podido consultar el tiempo: {exc.__class__.__name__}."
    if not geo.get("results"):
        return f"No encuentro la ciudad «{lugar}»."
    return geo["results"][0]


def _detectar_ubicacion() -> dict | None:
    """Ubicación de Windows (precisa); si no, ciudad por IP (aproximada)."""
    global _ubicacion_auto
    if _ubicacion_auto:
        return _ubicacion_auto

    coords = _windows_location()
    if coords:
        lat, lon = coords
        _ubicacion_auto = {
            "name": _nombre_lugar(lat, lon) or "tu ubicación",
            "latitude": lat,
            "longitude": lon,
        }
        return _ubicacion_auto

    for url in ("https://ipapi.co/json/", "http://ip-api.com/json/?fields=city,lat,lon"):
        try:
            datos = requests.get(url, timeout=6).json()
            ciudad = datos.get("city")
            lat = datos.get("latitude", datos.get("lat"))
            lon = datos.get("longitude", datos.get("lon"))
            if ciudad and lat is not None:
                _ubicacion_auto = {"name": ciudad, "latitude": lat, "longitude": lon}
                return _ubicacion_auto
        except (requests.RequestException, ValueError):
            continue
    return None


def _windows_location() -> tuple[float, float] | None:
    """lat/lon de la API de ubicación de Windows; None si está denegada."""
    try:
        import asyncio

        from winrt.windows.devices.geolocation import Geolocator

        async def obtener():
            estado = await Geolocator.request_access_async()
            if int(estado) != 1:  # 1 = ALLOWED
                return None
            posicion = await Geolocator().get_geoposition_async()
            punto = posicion.coordinate.point.position
            return punto.latitude, punto.longitude

        return asyncio.run(obtener())
    except Exception:
        return None


def _nombre_lugar(lat: float, lon: float) -> str | None:
    """Geocoding inverso gratuito y sin clave (BigDataCloud)."""
    try:
        datos = requests.get(
            "https://api.bigdatacloud.net/data/reverse-geocode-client",
            params={"latitude": lat, "longitude": lon, "localityLanguage": "es"},
            timeout=6,
        ).json()
        return datos.get("city") or datos.get("locality") or None
    except (requests.RequestException, ValueError):
        return None
