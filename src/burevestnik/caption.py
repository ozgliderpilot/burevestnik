"""Pure caption rendering. Takes a Forecast and a datetime, returns HTML string.

Telegram caption limit is 1024 chars; output must stay under that.
"""
import html
from datetime import datetime, timedelta

from burevestnik.models import Forecast


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


def _rain_band(peak_mm: float) -> str:
    """Map peak hourly rain (mm/h) to a band emoji.

    Bands: ≤1 🟢 (no umbrella), ≤5 🟡, ≤10 🟠, >10 🔴.
    """
    if peak_mm <= 1:
        return "🟢"
    if peak_mm <= 5:
        return "🟡"
    if peak_mm <= 10:
        return "🟠"
    return "🔴"


def _condition_emoji(title: str | None) -> str:
    """Map a meteoblue weather-pictogram alt text to a single emoji.

    Rules are checked in priority order — first match wins. Priority encodes
    "what to communicate above all else": severe weather > rain > clouds > clear.
    Unknown/empty/None titles fall back to 🌦.
    """
    if not title:
        return "🌦"
    t = title.lower()
    if "thunder" in t:
        return "⛈"
    if "snow" in t or "sleet" in t:
        return "🌨"
    if "fog" in t or "mist" in t:
        return "🌫"
    if "rain" in t or "shower" in t or "drizzle" in t:
        if "occasional" in t or "light" in t or "few" in t:
            return "🌦"
        return "🌧"
    if "overcast" in t:
        return "☁"
    if "mostly cloudy" in t:
        return "🌥"
    if "partly cloudy" in t:
        return "⛅"
    if "few clouds" in t:
        return "🌤"
    if "clear" in t:
        return "☀"
    return "🌦"


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


def render(
    forecast: Forecast,
    now: datetime,
    source_url: str,
    for_tomorrow: bool = False,
) -> str:
    primary = forecast.primary
    next_day_preview = forecast.next_day_preview

    # The displayed forecast date: shift +1 day in tomorrow-mode. The
    # "Updated HH:MM TZ" line below still uses `now` (actual run time).
    forecast_dt = now + timedelta(days=1) if for_tomorrow else now

    weekday_long = forecast_dt.strftime("%A")
    date_str = f"{forecast_dt.day} {forecast_dt.strftime('%B')}"

    sunrise, sunset = forecast.sunrise, forecast.sunset

    header_emoji = _condition_emoji(primary.condition)

    lines: list[str] = []
    if for_tomorrow:
        lines.append(f"{header_emoji} Tomorrow, {weekday_long} {date_str}")
    else:
        lines.append(f"{header_emoji} {weekday_long}, {date_str}")
    # No blank line here: keep the headline adjacent to the felt-temp line so
    # iPhone push-notification previews show both at a glance.
    lines.append(
        f"🤚🌡 High {round(forecast.temp_felt_max_c)}° / Low {round(forecast.temp_felt_min_c)}°"
    )

    if primary.rain_mm_high == 0:
        lines.append("☔ No rain")
    else:
        rain_str = _format_rain_range(primary.rain_mm_low, primary.rain_mm_high)
        rain_line = f"☔ Rain {rain_str}"
        if forecast.peak_rain_mm > 0:
            # Band emoji + "@HH:00" already signal a peak hourly value,
            # so the literal word "Peak" is omitted to keep the line short.
            rain_line += (
                f" · {_rain_band(forecast.peak_rain_mm)}"
                f" {_format_peak_mm(forecast.peak_rain_mm)}"
                f" @{forecast.peak_rain_time}"
            )
        lines.append(rain_line)

    if forecast.wind_kn_low == forecast.wind_kn_high:
        wind_str = f"{forecast.wind_kn_high}kn"
    else:
        wind_str = f"{forecast.wind_kn_low}–{forecast.wind_kn_high}kn"
    lines.append(f"💨 Wind {wind_str} · gusts to {forecast.gust_kn_max}kn")

    if sunrise is not None and sunset is not None:
        lines.append(
            f"☀ Sun {round(primary.sun_hours)}h · 🌅 {sunrise} · 🌇 {sunset}"
        )

    uv_emoji, uv_label = _uv_band(forecast.uv_index)
    lines.append(f"{uv_emoji} UV index {forecast.uv_index} ({uv_label})")

    if next_day_preview is not None:
        lines.append("")
        preview_rain = _format_rain_range(next_day_preview.rain_mm_low, next_day_preview.rain_mm_high)
        lines.append(
            f"<i>Tomorrow:</i> {round(next_day_preview.temp_max_c)}°/{round(next_day_preview.temp_min_c)}° "
            f"· {preview_rain} · wind {round(next_day_preview.wind_kn_max)}kn"
        )

    lines.append("")
    lines.append(
        f'<i>Updated {now.strftime("%H:%M %Z")} · '
        f'forecast by <a href="{html.escape(source_url, quote=True)}">meteoblue</a></i>'
    )

    return "\n".join(lines)
