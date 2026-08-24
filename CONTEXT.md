# Burevestnik

Telegram weather posts for a single city, scraped from meteoblue.

## Language

**Forecast day**:
The calendar day the daily post is about — Today or Tomorrow — switching at 16:00 local, together with that day's date. One fact shared by the fetch URL, the parsed tabs, and the caption header.
_Avoid_: today-mode, tomorrow-mode, for_tomorrow, run mode, displayed day, mode

**Forecast**:
The daily post's payload: a Forecast day, that day's summary and hourly metrics, and an optional next-day teaser. The teaser is absent when Forecast day is Tomorrow.
_Avoid_: daily forecast (ambiguous with Outlook)

**DaySummary**:
One day's tab on the meteoblue weekly view. Its Today/Tomorrow label is page text, not Forecast day.
_Avoid_: Forecast day, day (use Forecast day or DaySummary)

**Outlook**:
The extra 5-day post on Monday and Thursday mornings. A separate post that reads Forecast day (it only fires when Forecast day is Today); it is not a second encoding of Today/Tomorrow.
_Avoid_: 5-day forecast, weekly view
