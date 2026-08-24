from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum


class ForecastDayKind(Enum):
    TODAY = "today"
    TOMORROW = "tomorrow"


TOMORROW_CUTOFF_HOUR = 16  # 16:00 local — runs at/after this post tomorrow's forecast


@dataclass(frozen=True)
class ForecastDay:
    """The calendar day the daily post is about, plus that day's date.

    `page_index` is the meteoblue weekly-view day number: Today is #day1
    (no query string); Tomorrow is #day2 (`?day=2`).
    """

    kind: ForecastDayKind
    date: date

    @property
    def page_index(self) -> int:
        if self.kind is ForecastDayKind.TODAY:
            return 1
        return 2

    @classmethod
    def today(cls, d: date) -> "ForecastDay":
        return cls(kind=ForecastDayKind.TODAY, date=d)

    @classmethod
    def tomorrow(cls, d: date) -> "ForecastDay":
        return cls(kind=ForecastDayKind.TOMORROW, date=d)


def forecast_day(now: datetime) -> ForecastDay:
    """Return the Forecast day for a run at `now`.

    Cutoff is 16:00 inclusive in whatever timezone `now` carries
    (16:00:00 → Tomorrow, 15:59:59 → Today).
    """
    if now.hour >= TOMORROW_CUTOFF_HOUR:
        return ForecastDay.tomorrow(now.date() + timedelta(days=1))
    return ForecastDay.today(now.date())


@dataclass(frozen=True)
class DaySummary:
    label: str           # page text: "Today" / "Tomorrow" — not Forecast day
    weekday: str         # "Sun"
    temp_max_c: int
    temp_min_c: int
    wind_kn_max: int
    rain_mm_low: float
    rain_mm_high: float
    sun_hours: float
    condition: str | None = None  # day-pictogram alt, e.g. "Partly cloudy"; None if absent


@dataclass(frozen=True)
class Forecast:
    day: ForecastDay                 # which calendar day this forecast is about
    primary: DaySummary              # that day's tab summary
    next_day_preview: DaySummary | None  # next-day teaser; None when Forecast day is Tomorrow
    peak_rain_mm: float          # max hourly mm across the displayed day's precip row; 0.0 if dry
    peak_rain_time: str          # "HH:00" — the slot where peak hit; "" if no rain
    uv_index: int                # primary day's UV index (from page-level uv-index block)
    temp_felt_max_c: int         # max felt °C across the displayed day's temperature-felt row
    temp_felt_min_c: int         # min felt °C across the displayed day's temperature-felt row
    wind_kn_low: int             # min hourly wind kn across the displayed day's windspeed row
    wind_kn_high: int            # max hourly wind kn across the displayed day's windspeed row
    gust_kn_max: int             # max hourly gust kn across the displayed day's windgust row
    sunrise: str | None          # "HH:MM" from the page's sun-times block; None if missing
    sunset: str | None           # "HH:MM" from the page's sun-times block; None if missing
