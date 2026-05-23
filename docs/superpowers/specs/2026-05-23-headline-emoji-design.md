# Headline emoji in Telegram caption

## Problem

The Telegram caption posted by `burevestnik` opens with a hardcoded `🌦` regardless of the actual weather: a sunny day looks the same as a thunderstorm at a glance. We want the leading emoji on the Melbourne CBD header line to reflect the displayed day's conditions.

## Goal

Replace the hardcoded `🌦` in `caption.render` with an emoji derived from meteoblue's own weather pictogram for the displayed day. Sunny → ☀, overcast → ☁, rain → 🌧, etc.

## Non-goals

- Combining wind, heat, or UV warnings into the headline emoji. Wind / UV / felt-temp already have their own lines in the caption; the header stays single-emoji.
- Differentiating day vs night pictograms. The caption represents a whole day, so we always read meteoblue's `day` pictogram wrapper.
- Mapping by numeric pictocode (`03_iday`, `06_iday`, …). The `alt`/`title` text is human-readable, self-documenting, and lets us handle unseen labels by keyword instead of having to enumerate the full pictocode set.
- Showing a headline emoji for `next_day_preview`. The preview line stays plain text.

## Signal source

Each day tab in meteoblue's weekly view contains:

```html
<div class="weather-pictogram-wrapper day ">
  <img class="weather-pictogram " src=".../picto/03_iday.svg"
       alt="Partly cloudy" title="Partly cloudy">
</div>
```

We read the **`alt` text** (e.g. `"Partly cloudy"`, `"Overcast with rain"`) from the day-variant pictogram inside the relevant `#dayN` tab. The pictogram is per-day and lives inside the same `#dayN` element that `parse_day` already targets.

## Mapping rules

Implemented in a single function `_condition_emoji(title: str | None) -> str` in `caption.py`. The title is lowercased once, then each rule below is a case-insensitive substring check. **First match wins.** Rule order encodes priority — what should be communicated above all else.

| # | Keyword in lowercased title | Emoji | Notes |
|---|---|---|---|
| 1 | `thunder` | ⛈ | Severe — overrides anything else |
| 2 | `snow` or `sleet` | 🌨 | Frozen precip; rare in Melbourne CBD but possible |
| 3 | `fog` or `mist` | 🌫 | Visibility hazard |
| 4 | `rain`, `shower`, or `drizzle` | 🌧 / 🌦 | Sub-rule: 🌦 if the title also contains `occasional`, `light`, or `few`; else 🌧 |
| 5 | `overcast` | ☁ | Solid grey, no precip in label |
| 6 | `mostly cloudy` | 🌥 | Sun mostly hidden |
| 7 | `partly cloudy` | ⛅ | Mixed sun and cloud |
| 8 | `few clouds` | 🌤 | Matches "Clear and few clouds" before rule 9 — order matters |
| 9 | `clear` | ☀ | Cloudless |
| — | fallback (incl. `None`) | 🌦 | Preserves the current default for any unrecognized title |

### Verifying against every label observed in `tests/fixtures/meteoblue.html`

| meteoblue `alt` | Matched rule | Emoji |
|---|---|---|
| `Clear, cloudless sky` | 9 | ☀ |
| `Clear and few clouds` | 8 (wins before 9) | 🌤 |
| `Partly cloudy` | 7 | ⛅ |
| `Overcast` | 5 | ☁ |
| `Overcast with rain` | 4, no "occasional" | 🌧 |
| `Overcast with occasional rain` | 4 + "occasional" | 🌦 |
| `Mostly cloudy with occasional rain` | 4 + "occasional" | 🌦 |
| `Mostly cloudy` *(observed for night, day variant exists)* | 6 | 🌥 |

### Verifying against plausible unseen labels

| Hypothetical `alt` | Matched rule | Emoji |
|---|---|---|
| `Mostly cloudy with thunderstorms` | 1 (thunder wins) | ⛈ |
| `Light rain` | 4 + "light" | 🌦 |
| `Heavy rain` | 4, no sub-keyword | 🌧 |
| `Few showers` | 4 + "few" | 🌦 |
| `Fog` | 3 | 🌫 |
| `Light snow showers` | 2 (snow wins over rain sub-rule) | 🌨 |
| *(empty string or `None`)* | fallback | 🌦 |

## Code changes

### `src/burevestnik/models.py`

Add one optional field to `DaySummary`:

```python
condition: str | None  # raw meteoblue pictogram alt text, e.g. "Partly cloudy"; None if missing
```

`Forecast` is unchanged — the caption reads `forecast.primary.condition`. `next_day_preview.condition` is populated for symmetry but currently unused.

### `src/burevestnik/parse.py`

Extend `parse_day(html, selector)` to also extract the pictogram. After the existing text/regex extraction, look up the day pictogram inside the same `el`:

```python
pic = el.css_first(".weather-pictogram-wrapper.day img.weather-pictogram")
condition = pic.attributes.get("alt") if pic is not None else None
```

Pass `condition=condition` into the `DaySummary` constructor. No new top-level helper, no change to `extract`'s signature, no change elsewhere in `parse.py`.

A missing wrapper or missing `alt` yields `None`; the caption's mapping function handles `None` via the fallback rule.

### `src/burevestnik/caption.py`

1. Add `_condition_emoji(title: str | None) -> str` implementing the priority table above. Returns `"🌦"` for `None` or no match.
2. In `render`, replace the hardcoded `🌦` in **both** Melbourne CBD header lines (today-mode and tomorrow-mode) with `_condition_emoji(forecast.primary.condition)`.

No other lines in the caption change. The 1024-char Telegram caption budget is unaffected — we're substituting one single-character emoji for another.

## Tests

### New: `_condition_emoji` unit tests (`tests/test_caption.py`)

Table-driven test covering every row in both verification tables above (observed labels + hypothetical unseen labels), plus the `None`/empty-string fallback cases.

### Extended: `parse_day` test (`tests/test_parse.py`)

Add an assertion that the returned `DaySummary.condition` equals the expected `alt` text for `#day1` in the fixture (and likewise for `#day2`). The other fixture-derived parse tests are unaffected.

### Existing caption tests

Any test that asserts on the leading character of the Melbourne CBD header line (currently `🌦`) needs its expected value updated to whatever the fixture's `#day1` pictogram alt maps to (`"Partly cloudy"` → ⛅, per the table above). Tests that don't inspect the header emoji are unaffected.

## Risks and mitigations

- **meteoblue renames or localizes the `alt` text.** Mitigation: the keyword-priority rules (`thunder`, `snow`, `rain`, `overcast`, `cloudy`, `clear`) are deliberately broad and survive minor wording changes. Any title we can't classify falls back to the current default 🌦, so the caption never breaks — it just degrades to the pre-change behavior.
- **meteoblue ships a brand-new `alt` we haven't planned for.** Same fallback path; caption stays valid.
- **The pictogram wrapper is missing entirely.** `condition` is `None`, fallback emoji is used.

## Acceptance criteria

1. Running the bot on the fixture-equivalent of today's `#day1` ("Partly cloudy") posts a caption whose first character is ⛅, not 🌦.
2. Each label in the verification tables above produces the listed emoji.
3. A missing pictogram (`condition is None`) produces 🌦 — the caption is never broken by the change.
4. `uv run pytest` passes.
