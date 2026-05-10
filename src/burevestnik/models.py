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
    peak_rain_mm: float          # max hourly mm across the displayed day's precip row; 0.0 if dry
    peak_rain_time: str          # "HH:00" — the slot where peak hit; "" if no rain
    uv_index: int                # primary day's UV index (from page-level uv-index block)
    temp_felt_max_c: int         # max felt °C across the displayed day's temperature-felt row
    temp_felt_min_c: int         # min felt °C across the displayed day's temperature-felt row
