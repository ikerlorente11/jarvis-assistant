"""Tiempo con Open-Meteo: API gratuita sin clave (geocoding + forecast).

La ciudad sale de config.yaml (`city:`); con `auto` (o vacío) se detecta por
IP una vez por sesión. Siempre se puede pedir otra: "qué tiempo hace en X".
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

_ciudad_ip: str | None = None  # caché de la detección por IP (una por sesión)


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

    actual = datos["current"]
    diario = datos["daily"]
    cielo = WMO.get(actual["weather_code"], "")
    return (
        f"En {sitio['name']}: {round(actual['temperature_2m'])}°C"
        + (f", {cielo}" if cielo else "")
        + f". Máxima {round(diario['temperature_2m_max'][0])}°, "
        f"mínima {round(diario['temperature_2m_min'][0])}°. "
        f"Viento {round(actual['wind_speed_10m'])} km/h."
    )


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

    diario = datos["daily"]
    lineas = []
    for i, fecha in enumerate(diario["time"]):
        dt = datetime.strptime(fecha, "%Y-%m-%d")
        cielo = WMO.get(diario["weather_code"][i], "")
        lluvia = diario.get("precipitation_probability_max")
        prob = f", lluvia {lluvia[i]}%" if lluvia and lluvia[i] is not None else ""
        lineas.append(
            f"{DIAS_SEMANA[dt.weekday()]} {dt.day}: "
            f"{round(diario['temperature_2m_min'][i])}-"
            f"{round(diario['temperature_2m_max'][i])}°, {cielo}{prob}"
        )
    return f"Previsión en {sitio['name']}:\n" + "\n".join(lineas)


def _geolocalizar(config: dict, ciudad: str | None) -> dict | str:
    """Nombre de ciudad → dict de Open-Meteo geocoding; str = mensaje de error."""
    lugar = (ciudad or config.get("city") or "auto").strip()
    if lugar.lower() == "auto":
        lugar = _ciudad_por_ip()
        if lugar is None:
            return ("No he podido detectar tu ciudad por IP. "
                    "Pon `city: TuCiudad` en config.yaml.")
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


def _ciudad_por_ip() -> str | None:
    global _ciudad_ip
    if _ciudad_ip:
        return _ciudad_ip
    for url in ("https://ipapi.co/json/", "http://ip-api.com/json/?fields=city"):
        try:
            ciudad = requests.get(url, timeout=6).json().get("city")
            if ciudad:
                _ciudad_ip = ciudad
                return ciudad
        except (requests.RequestException, ValueError):
            continue
    return None
