# 5-day outlook post (Monday & Thursday)

## Problem

`burevestnik` posts a single-day forecast twice a day. There is no at-a-glance
view of the days ahead. We want a 5-day outlook: on Monday and Thursday
mornings, post a cropped 5-day temperature chart plus a compact per-day text
summary, sent **before** the normal "today" forecast.

## Goal

On the Monday **and** Thursday morning runs, post one extra Telegram photo
message:

- **Image:** the meteoblue meteogram ("Hourly weather forecast for Melbourne
  CBD"), cropped vertically to its **top temperature panel** across all 5 days.
- **Caption:** a compact one-line-per-day summary for the next 5 days, built from
  the same `DaySummary` data the daily caption already parses.

Because the page's `#day1` is always *today*, the 5 days follow naturally from
the run date: Monday → Mon–Fri, Thursday → Thu–Mon. The normal daily forecast
then posts as usual, unchanged.

## Non-goals

- **No posting cadence beyond Monday/Thursday mornings.** The *evening* runs
  (tomorrow-mode) and all other days are untouched. Manual `workflow_dispatch`
  runs follow the same time-based rule.
- **No hourly-table-derived metrics in the outlook caption.** Felt temp, gusts,
  UV index, sunrise/sunset are single-day values from `table.hourlywind`; the
  outlook summary uses only `DaySummary` fields (condition, hi/lo, rain low–high,
  sun hours). Wind max is available but deliberately omitted (see caption rules).
- **No horizontal cropping of the chart.** The meteogram is natively a 5-day
  graph, so only the vertical crop (drop the cloud + wind panels) is needed.
- **No retargeting of the cron.** Trigger is derived from `now` in
  `FORECAST_TZ`, like the existing today/tomorrow cutoff. The morning cron
  already fires every day; the helper just selects Mon/Thu.

## Trigger

The outlook post fires when it is **Monday or Thursday** in `FORECAST_TZ`
**and** the run is in today-mode (before the 16:00 cutoff) — i.e. the ~04:17
Melbourne morning cron. The evening runs are tomorrow-mode and are excluded.

A new pure helper in `main.py`, mirroring the existing `should_forecast_tomorrow`:

```python
_OUTLOOK_WEEKDAYS = (0, 3)  # Monday, Thursday

def should_post_outlook(now: datetime) -> bool:
    """True on the Monday/Thursday morning (today-mode) runs only."""
    return now.weekday() in _OUTLOOK_WEEKDAYS and not should_forecast_tomorrow(now)
```

`main()` checks this **before** the daily flow. On a match it posts the outlook
first, then continues to the unchanged daily post.

### Failure isolation (best-effort outlook)

The outlook branch is wrapped in `try/except`. On any failure it prints a loud
warning (visible in Actions logs) and **continues to the daily post**. The core
daily forecast is never blocked by a problem in the outlook extra. This is a
deliberate, local divergence from the codebase's otherwise fail-loud norm,
justified because the daily forecast is the primary product and the outlook is a
twice-a-week nicety.

## Caption format

Approved "Option A — compact one line per day", trimmed to fit a single mobile
line: no header, no wind field, space-separated (no middots):

```
⛅ Thu 17°/10° ☔ 1–3mm ☀ 4h
☀ Fri 18°/15° no rain ☀ 8h
🌧 Sat 16°/12° ☔ 5–10mm ☀ 2h
⛅ Sun 17°/11° no rain ☀ 6h
☀ Mon 19°/13° no rain ☀ 9h

Updated 04:17 AEST · forecast by meteoblue
```

(Example shows a Thursday run; a Monday run would read Mon–Fri.)

Rules:

- **No header line.** The caption opens directly with the first day so the
  push-notification preview leads with real data.
- **Per day** (one line each, fields separated by a single space, no middots):
  - condition emoji via the existing `_condition_emoji(DaySummary.condition)`
  - weekday short label from `DaySummary.weekday` (matches the chart's labels)
  - `{temp_max_c}°/{temp_min_c}°`
  - rain: `no rain` when `rain_mm_high == 0`, else
    `☔ {_format_rain_range(rain_mm_low, rain_mm_high)}`
  - `☀ {round(sun_hours)}h`
  - **Wind is omitted** to keep each day to one mobile line.
- **Footer:** identical to the daily caption —
  `<i>Updated HH:MM TZ · forecast by <a href="…">meteoblue</a></i>`, using `now`
  and the unmodified source URL.
- Output must stay under Telegram's 1024-char caption limit (5 days fits
  comfortably).

`render_outlook` is a pure function in `caption.py` reusing `_condition_emoji`
and `_format_rain_range`.

## Image: cropping the meteogram

The chart is the `#meteogram` section, heading "Hourly weather forecast for
Melbourne CBD". It is a JS-hydrated Highcharts graph (`div#blooimage`, ~650px
tall) stacking three panels: **temperature** (top), clouds/precip (middle), wind
(bottom). The static test fixture contains only `<div class="loading"></div>` —
the chart renders client-side — so the crop **cannot be unit-tested** and is
verified via `workflow_dispatch`, exactly like today's `table.hourlywind`
screenshot.

New `scrape.fetch_meteogram(url) -> tuple[str, bytes]`:

1. Reuse the existing unit-cookie seeding and consent-overlay killer. Extract the
   shared browser/context/page boilerplate out of `fetch` into a small private
   helper (e.g. a `_prepared_context` context manager) so both `fetch` and
   `fetch_meteogram` share it rather than copy-pasting.
2. Navigate, then wait for the Highcharts meteogram to finish hydrating (the
   `#blooimage` chart content present, `.loading` gone).
3. Screenshot a **vertical clip** of the meteogram element: full width, top
   fraction only. The fraction is a **named constant** tuned so the clip lands on
   the temperature/cloud-panel boundary (matching the crop sample). Returns the
   page HTML (for `parse_days`) and the cropped JPEG.

**Implementation risk (flagged):** the exact clip fraction must be tuned against
a live render during implementation, since it isn't covered by the fixture-based
tests. This is the one part that needs manual visual verification before merge.

## Parsing 5 days

New pure `parse.parse_days(html, count=5) -> list[DaySummary]` that loops the
existing `parse_day` over `#day1`…`#day{count}`. No new field logic — the fixture
already carries `#day1`–`#day7`, so this is fully unit-testable. `#day1` is today,
so the list is the next 5 days in order from the run date.

## Data flow

```
main.py (outlook branch — Mon/Thu AM)
  scrape.fetch_meteogram(url)            →  (html, cropped_jpeg)   [browser I/O]
  parse.parse_days(html, 5)             →  list[DaySummary]        [pure]
  caption.render_outlook(days, now, url) → caption str             [pure]
  telegram.send_photo(token, chat_id, cropped_jpeg, caption)

  …then the existing daily flow runs unchanged.
```

The outlook branch does its own `fetch_meteogram` (one extra browser launch,
twice a week) and is fully self-contained, keeping the normal daily path
untouched.

## Testing

- `parse_days`: against the fixture — returns 5 `DaySummary`, correct values and
  order.
- `render_outlook`: exact format; `no rain` line when dry; sun-hours rounding;
  footer stamp from `now`; output < 1024 chars.
- `should_post_outlook`: Monday and Thursday before cutoff → `True`; Mon/Thu at
  or after cutoff → `False`; other weekdays (any hour) → `False`.
- `fetch_meteogram`: not unit-tested (JS-hydrated chart); verified via
  `workflow_dispatch` against the live channel — consistent with the existing
  screenshot path.

## CI behavior

No workflow changes. The existing `schedule` / `workflow_dispatch` path runs the
full pipeline; `main()` decides internally whether the outlook branch fires. The
`push` path still runs `pytest` only, now covering the new pure functions.
