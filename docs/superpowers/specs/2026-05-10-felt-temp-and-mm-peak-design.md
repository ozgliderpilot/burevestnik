# Felt-temperature headline + mm-based rain peak

Status: approved 2026-05-10

## Summary

Two caption changes that move from "what the thermostat says" toward "what the day will feel like":

1. The headline High/Low becomes the **felt** temperature (read from `tr.temperature-felt` in the hourly table) and the icon picks up a hand: `🤚🌡 High 18° / Low 10°`.
2. The rain peak switches from precipitation **probability** (`tr.precip-prop`, %) to precipitation **amount** (`tr.precip`, mm). The rain line is now always emitted — including a `☔ No rain` form on dry days.

## Caption shapes

**Wet day, non-zero hourly mm**
```
🤚🌡 High 18° / Low 10°
☔ Rain 0–2mm · Peak 1.5mm at 14:00
```

**Wet probability but every hourly mm cell is empty/0** (the current fixture)
```
🤚🌡 High 18° / Low 10°
☔ Rain 0–2mm
```

**Daily mm range itself is 0**
```
🤚🌡 High 18° / Low 10°
☔ No rain
```

## Data model (`models.py`)

`Forecast` changes:

| field | change | type | source |
| --- | --- | --- | --- |
| `temp_felt_max_c` | **add** | `int` | max of `tr.temperature-felt` cells |
| `temp_felt_min_c` | **add** | `int` | min of `tr.temperature-felt` cells |
| `peak_rain_pct` | **remove** | — | — |
| `peak_rain_mm` | **add** | `float` | max of `tr.precip` cells |
| `peak_rain_time` | keep | `str` | now references the hour of the mm peak |

Felt high/low live on `Forecast` (not `DaySummary`) because the hourly table only covers the displayed primary day. In `tomorrow-mode` the page is fetched with `?day=2`, so the row already reflects tomorrow — same scoping `parse_peak_rain` already relied on.

`DaySummary` is unchanged. The `Forecast.tomorrow` preview line keeps the *actual* high/low because no hourly felt data is available for the secondary day in today-mode.

## Parser (`parse.py`)

Two new pure functions, both reading `table.hourlywind`:

- `parse_temp_felt(html) -> tuple[int, int]`
  - Locate `tr.temperature-felt`; iterate `<td>` cells; for each, parse the leading integer before `°` (e.g. `10°` → `10`).
  - Return `(max, min)`. Raise `ValueError` if the row is missing or yields zero numeric cells.

- `parse_peak_rain_mm(html) -> tuple[float, str]`
  - Locate `tr.precip`. For each `<td>`, read the inner span text; parse a float if present, else treat as 0.
  - Reuse the same hour-label extraction `parse_peak_rain` does (digits → `HH:00`).
  - Return `(max_mm, "HH:00")` with earliest-hour tie-break. Return `(0.0, "")` when every cell is empty/zero. Raise `ValueError` when the row itself is missing.

`extract()` calls both new functions, drops `parse_peak_rain`, and populates the new `Forecast` fields. The old probability-based `parse_peak_rain` is removed (nothing else references it).

## Caption (`caption.py`)

Thermometer line — no `<b>` around the value:
```python
f"🤚🌡 High {round(forecast.temp_felt_max_c)}° / Low {round(forecast.temp_felt_min_c)}°"
```

Rain line — always emitted (bold on the peak value preserved from the current `<b>{pct}%</b>` style):
```python
if today.rain_mm_high == 0:
    lines.append("☔ No rain")
else:
    line = f"☔ Rain {_format_rain_range(today.rain_mm_low, today.rain_mm_high)}"
    if forecast.peak_rain_mm > 0:
        line += f" · Peak <b>{_format_peak_mm(forecast.peak_rain_mm)}</b> at {forecast.peak_rain_time}"
    lines.append(line)
```

Peak-mm formatting — one decimal place with trailing zero stripped:
- `0.5` → `0.5mm`
- `1.5` → `1.5mm`
- `12.0` → `12mm`

Implementation: `f"{round(mm, 1):g}mm"` (the `:g` format strips the trailing zero).

## What is NOT changing

- `DaySummary.temp_max_c/min_c` keep their meaning (actual temps).
- The Tomorrow-preview line continues to show actual high/low.
- Wind, sun, UV, sunrise/sunset lines are untouched.
- `_format_rain_range` is untouched (still integer-rounded).

## Tests

Existing tests touched:
- `test_caption.py` fixtures: replace `peak_rain_pct` with `peak_rain_mm`, add `temp_felt_max_c/min_c` to `Forecast` constructions; update assertions for the `🤚🌡` headline and the new rain-line shapes (including `No rain`).
- `test_parse.py` end-to-end: assert `forecast.peak_rain_mm == 0.0` for the existing fixture (which has empty `tr.precip`) and add a sanity range for `temp_felt_max_c/min_c`.

New tests:
- `parse_temp_felt` against the fixture: assert exact `(max, min)` pulled from `tr.temperature-felt`.
- `parse_peak_rain_mm` against the fixture: returns `(0.0, "")`.
- A small synthetic-HTML test with two non-zero mm cells to verify max selection + earliest-hour tie-break.
- Caption: rendering with `peak_rain_mm = 1.5` includes `Peak 1.5mm at HH:00`; with `peak_rain_mm = 12.0` it renders `12mm` (no trailing zero); with `rain_mm_high == 0` it renders `☔ No rain`.

## Doc updates

`CLAUDE.md` — remove the obsolete diagnostic-signal note about "0mm alongside Peak N%". Replace the `parse_peak_rain` paragraph with one sentence describing `parse_peak_rain_mm` and `parse_temp_felt`, both of which derive from the same `table.hourlywind` whose contents already track the displayed day.
