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


def _format_peak_mm(mm: float) -> str:
    """Format hourly mm with one decimal, stripping a trailing zero.

    0.5 -> "0.5mm"; 1.5 -> "1.5mm"; 12.0 -> "12mm".
    """
    return f"{round(mm, 1):g}mm"


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
    lines.append(
        f"🤚🌡 High {round(forecast.temp_felt_max_c)}° / Low {round(forecast.temp_felt_min_c)}°"
    )

    if today.rain_mm_high == 0:
        lines.append("☔ No rain")
    else:
        rain_str = _format_rain_range(today.rain_mm_low, today.rain_mm_high)
        rain_line = f"☔ Rain {rain_str}"
        if forecast.peak_rain_mm > 0:
            rain_line += (
                f" · Peak {_format_peak_mm(forecast.peak_rain_mm)}"
                f" at {forecast.peak_rain_time}"
            )
        lines.append(rain_line)

    if forecast.wind_kn_low == forecast.wind_kn_high:
        wind_str = f"{forecast.wind_kn_high}kn"
    else:
        wind_str = f"{forecast.wind_kn_low}–{forecast.wind_kn_high}kn"
    lines.append(f"💨 Wind {wind_str} · gusts to {forecast.gust_kn_max}kn")

    if sunrise is not None and sunset is not None:
        lines.append(
            f"☀ Sun {round(today.sun_hours)}h · 🌅 {sunrise} · 🌇 {sunset}"
        )

    uv_emoji, uv_label = _uv_band(forecast.uv_index)
    lines.append(f"UV index: {uv_emoji} {forecast.uv_index} ({uv_label})")

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
