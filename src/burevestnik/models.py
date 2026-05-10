from dataclasses import dataclass


@dataclass(frozen=True)
class DaySummary:
    label: str           # "Today" / "Tomorrow"
    weekday: str         # "Sun"
    temp_max_c: int
    temp_min_c: int
    wind_kn_max: int
    rain_mm_low: float
    rain_mm_high: float
    sun_hours: float


@dataclass(frozen=True)
class Forecast:
    today: DaySummary
    tomorrow: DaySummary | None  # None when running in tomorrow-mode (post-16:00)
    peak_rain_pct: int          # max % across the displayed day's 1-hour slots
    peak_rain_time: str         # "HH:MM" — the slot where peak hit; "" if no rain
