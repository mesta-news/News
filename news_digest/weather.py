"""Today's weather for the Today page (Open-Meteo: free, no API key)."""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
       "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
       "wind_speed_10m_max&timezone=Europe%2FAmsterdam&forecast_days=1")

# WMO weather codes -> (emoji, words)
CODES = {0: ("☀️", "Clear"), 1: ("🌤️", "Mostly clear"), 2: ("⛅", "Partly cloudy"), 3: ("☁️", "Overcast"),
         45: ("🌫️", "Fog"), 48: ("🌫️", "Fog"), 51: ("🌦️", "Light drizzle"), 53: ("🌦️", "Drizzle"),
         55: ("🌧️", "Heavy drizzle"), 61: ("🌦️", "Light rain"), 63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
         66: ("🌧️", "Freezing rain"), 67: ("🌧️", "Freezing rain"), 71: ("🌨️", "Light snow"), 73: ("🌨️", "Snow"),
         75: ("❄️", "Heavy snow"), 77: ("🌨️", "Snow grains"), 80: ("🌦️", "Showers"), 81: ("🌧️", "Showers"),
         82: ("⛈️", "Heavy showers"), 85: ("🌨️", "Snow showers"), 86: ("🌨️", "Snow showers"),
         95: ("⛈️", "Thunderstorms"), 96: ("⛈️", "Thunderstorms, hail"), 99: ("⛈️", "Thunderstorms, hail")}


def today(place: dict | None) -> dict | None:
    if not place:
        return None
    try:
        day = requests.get(URL.format(lat=place["lat"], lon=place["lon"]), timeout=20).json()["daily"]
        code = day["weather_code"][0]
        emoji, words = CODES.get(code, ("🌡️", ""))
        return {"place": place.get("name", ""), "emoji": emoji, "text": words,
                "max": round(day["temperature_2m_max"][0]), "min": round(day["temperature_2m_min"][0]),
                "rain": day["precipitation_probability_max"][0], "wind": round(day["wind_speed_10m_max"][0])}
    except Exception as exc:
        log.warning("weather: %s", exc)
        return None
