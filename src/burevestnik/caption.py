"""Pure caption rendering. Takes a Forecast and a datetime, returns HTML string.

Telegram caption limit is 1024 chars; output must stay under that.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun

from burevestnik.models import Forecast

MELBOURNE = LocationInfo(
    name="Melbourne",
    region="Australia",
    timezone="Australia/Melbourne",
    latitude=-37.81,
    longitude=144.96,
)
MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")


def _format_rain_range(low: float, high: float) -> str:
    low_i, high_i = round(low), round(high)
    if low_i == high_i:
        return f"{low_i}mm"
    return f"{low_i}–{high_i}mm"


def _uv_band(uv: int) -> tuple[str, str]:
    """Map a UV index to (emoji, risk label) per WHO bands.

    Bands: 0-2 Low, 3-5 Moderate, 6-7 High, 8-10 Very High, 11+ Extreme.
    """
    if uv <= 2:
        return "🟢", "Low"
    if uv <= 5:
        return "🟡", "Moderate"
    if uv <= 7:
        return "🟠", "High"
    if uv <= 10:
        return "🔴", "Very High"
    return "🟣", "Extreme"


def _sunrise_sunset(now: datetime) -> tuple[str, str] | tuple[None, None]:
    try:
        s = sun(MELBOURNE.observer, date=now.date(), tzinfo=MELBOURNE_TZ)
        return s["sunrise"].strftime("%H:%M"), s["sunset"].strftime("%H:%M")
    except (ValueError, KeyError):
        return None, None


def render(
    forecast: Forecast,
    now: datetime,
    source_url: str,
    for_tomorrow: bool = False,
) -> str:
    today = forecast.today
    tomorrow = forecast.tomorrow

    # The displayed forecast date: shift +1 day in tomorrow-mode. The
    # "Updated HH:MM TZ" line below still uses `now` (actual run time).
    forecast_dt = now + timedelta(days=1) if for_tomorrow else now

    weekday_long = forecast_dt.strftime("%A")
    date_str = f"{forecast_dt.day} {forecast_dt.strftime('%B')}"

    sunrise, sunset = _sunrise_sunset(forecast_dt)

    lines: list[str] = []
    if for_tomorrow:
        lines.append(
            f"🌦 <b>Melbourne CBD</b> · Tomorrow, {weekday_long} {date_str}"
        )
    else:
        lines.append(
            f"🌦 <b>Melbourne CBD</b> · {weekday_long}, {date_str}"
        )
    lines.append("")
    lines.append(f"🌡 High <b>{round(today.temp_max_c)}°</b> / Low {round(today.temp_min_c)}°")

    if forecast.peak_rain_pct > 0:
        rain_str = _format_rain_range(today.rain_mm_low, today.rain_mm_high)
        lines.append(
            f"☔ Rain {rain_str} · Peak <b>{forecast.peak_rain_pct}%</b> "
            f"at {forecast.peak_rain_time}"
        )

    lines.append(f"💨 Wind up to {round(today.wind_kn_max)}kn")

    if sunrise is not None and sunset is not None:
        lines.append(
            f"☀ Sun {round(today.sun_hours)}h · 🌅 {sunrise} · 🌇 {sunset}"
        )

    if tomorrow is not None:
        lines.append("")
        tomorrow_rain = _format_rain_range(tomorrow.rain_mm_low, tomorrow.rain_mm_high)
        lines.append(
            f"<i>Tomorrow:</i> {round(tomorrow.temp_max_c)}°/{round(tomorrow.temp_min_c)}° "
            f"· {tomorrow_rain} · wind {round(tomorrow.wind_kn_max)}kn"
        )

    lines.append("")
    lines.append(
        f'<i>Updated {now.strftime("%H:%M %Z")} · '
        f'forecast by <a href="{source_url}">meteoblue</a></i>'
    )

    return "\n".join(lines)
