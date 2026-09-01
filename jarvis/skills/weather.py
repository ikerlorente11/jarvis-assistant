"""Tiempo con Open-Meteo: API gratuita sin clave (geocoding + forecast)."""

from __future__ import annotations

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


def hoy(config: dict, ciudad: str | None = None) -> str:
    lugar = (ciudad or config.get("city", "")).strip()
    if not lugar:
        return "No sé qué ciudad mirar: añade `city:` a config.yaml."
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": lugar, "count": 1, "language": "es"},
            timeout=6,
        ).json()
        if not geo.get("results"):
            return f"No encuentro la ciudad «{lugar}»."
        sitio = geo["results"][0]
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
