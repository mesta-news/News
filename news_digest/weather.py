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
        return {"place": place.get("name", ""), "emoji": emoji, "text": words, "code": code,
                "max": round(day["temperature_2m_max"][0]), "min": round(day["temperature_2m_min"][0]),
                "rain": day["precipitation_probability_max"][0], "wind": round(day["wind_speed_10m_max"][0])}
    except Exception as exc:
        log.warning("weather: %s", exc)
        return None


# Line icons for the Today card, the same drawings as the forecast screen in app.js.
ICONS = {
    "sun": '<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>',
    "part": '<path d="M8 4v1.5M3.5 8.5H5M4.8 4.8l1 1M12.2 4.8l-1 1"/><path d="M5.6 10.6A3.5 3.5 0 1 1 11.6 7"/><path d="M8 20h9a4 4 0 0 0 0-8 5.5 5.5 0 0 0-10.4 2A3 3 0 0 0 8 20z"/>',
    "cloud": '<path d="M7 19h10a4.5 4.5 0 0 0 .4-9A6 6 0 0 0 6 11.5 3.8 3.8 0 0 0 7 19z"/>',
    "fog": '<path d="M7 13h10a4 4 0 0 0 .3-8A5.5 5.5 0 0 0 6.6 6.8 3.2 3.2 0 0 0 7 13z"/><path d="M4 17h16M6 20.5h12"/>',
    "rain": '<path d="M7 15h10a4 4 0 0 0 .3-8A5.5 5.5 0 0 0 6.6 8.8 3.2 3.2 0 0 0 7 15z"/><path d="M8.5 18l-1 2.5M12.5 18l-1 2.5M16.5 18l-1 2.5"/>',
    "snow": '<path d="M7 14h10a4 4 0 0 0 .3-8A5.5 5.5 0 0 0 6.6 7.8 3.2 3.2 0 0 0 7 14z"/><path d="M8.5 18.5h.01M12 20.5h.01M15.5 18.5h.01"/>',
    "storm": '<path d="M7 14h10a4 4 0 0 0 .3-8A5.5 5.5 0 0 0 6.6 7.8 3.2 3.2 0 0 0 7 14z"/><path d="M12.5 15l-2.5 4h3.5l-2 4"/>',
}
EMOJI_KIND = {"☀️": "sun", "🌤️": "sun", "⛅": "part", "☁️": "cloud", "🌫️": "fog", "🌦️": "rain", "🌧️": "rain",
              "🌨️": "snow", "❄️": "snow", "⛈️": "storm"}


def kind(w: dict) -> str:
    """Icon family for a weather dict (WMO code when stored, else the older emoji)."""
    c = w.get("code")
    if c is None:
        return EMOJI_KIND.get(w.get("emoji", ""), "cloud")
    if c <= 1:
        return "sun"
    if c == 2:
        return "part"
    if c == 3:
        return "cloud"
    if c <= 48:
        return "fog"
    if c >= 95:
        return "storm"
    if 71 <= c <= 77 or c in (85, 86):
        return "snow"
    return "rain"


def icon_svg(w: dict) -> str:
    k = kind(w)
    return (f'<svg class="wx-icon wxi-{k}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[k]}</svg>')
