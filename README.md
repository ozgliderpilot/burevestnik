# Burevestnik

[![post](https://github.com/ozgliderpilot/burevestnik/actions/workflows/post.yml/badge.svg)](https://github.com/ozgliderpilot/burevestnik/actions/workflows/post.yml)

Burevestnik (буревестник, "stormy petrel") is a small bot that flies to meteoblue twice a day, screenshots Melbourne CBD's hourly forecast, and squawks the result into a Telegram channel.

<img src="docs/example-post.png" alt="drawing" width="452"/>

## How it flies

```
scrape (Playwright)  →  parse (HTML → Forecast)  →  caption (Forecast → str)  →  send (Telegram)
```

Side effects live at the edges; the middle is pure and tested against a fixed HTML fixture. A GitHub Actions cron flaps the wings every 12 hours.

## Run it yourself

```sh
uv sync --extra dev --frozen
uv run playwright install chromium
uv run python -m burevestnik.main
```

Env vars:

| Name                  | Required | Default                                  | Notes                                                                     |
|-----------------------|----------|------------------------------------------|---------------------------------------------------------------------------|
| `TELEGRAM_BOT_TOKEN`  | yes      | —                                        | Bot token from BotFather.                                                 |
| `TELEGRAM_CHAT_ID`    | yes      | —                                        | Numeric (`-100…`) or `@channel_username`.                                 |
| `METEOBLUE_URL`       | no       | Melbourne CBD weekly view                | Any meteoblue weekly-view URL. The `?day=2` swap is appended automatically. |
| `FORECAST_TZ`         | no       | `Australia/Melbourne`                    | IANA timezone name; controls the today/tomorrow cutoff (16:00 local) and the "Updated HH:MM TZ" caption stamp. |

For architecture invariants, CI modes, and parser internals, see [CLAUDE.md](CLAUDE.md).
