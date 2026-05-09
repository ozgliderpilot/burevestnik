# Burevestnik

Telegram bot that posts a 1-hourly weather forecast for North Melbourne to a private channel, 5 times per day. Runs on GitHub Actions cron — no server needed.

See `meteo-plan.md` for full design rationale; `meteo-implementation-plan.md` for build steps.

## What it posts

- A JPEG screenshot of meteoblue's 1-hourly forecast table.
- A rich text caption with today's high/low, peak rain probability and time, wind, sunrise/sunset, and a one-line tomorrow brief.

Posting times (Melbourne local): **06:00, 09:00, 12:00, 15:00, 18:00**, every day. DST is handled automatically.

## One-time setup

### 1. Create the Telegram bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram → send `/newbot`.
2. Choose a name and username (must end in `bot`).
3. **Save the token** that BotFather gives you — looks like `123456:ABC-DEF...`.

### 2. Create the channel

1. In Telegram → New Channel → **Private**.
2. Open the channel → settings → Administrators → Add admin → search your bot's username → grant **Post Messages** only (no other permissions needed).

### 3. Get the channel ID

1. Post any message in your new channel from your own account.
2. Forward that message to [@RawDataBot](https://t.me/RawDataBot) (or [@JsonDumpBot](https://t.me/JsonDumpBot)).
3. The bot returns a JSON dump. Find `forward_from_chat.id` — it's a negative integer like `-1001234567890`. **Save it.**

### 4. Configure the GitHub repo

1. Push this repo to GitHub (private is fine).
2. Repo settings → Secrets and variables → Actions → New repository secret. Add:
   - `TELEGRAM_BOT_TOKEN` — the bot token from step 1.
   - `TELEGRAM_CHAT_ID` — the channel ID from step 3.
3. Actions → "Post weather to Telegram" → Run workflow → manually trigger once to verify.

After verification, the cron schedule takes over.

## Local development

```powershell
uv sync --extra dev
uv run playwright install chromium
uv run pytest
```

Run a one-off post locally (requires both env vars set):

```powershell
$env:TELEGRAM_BOT_TOKEN = "..."
$env:TELEGRAM_CHAT_ID = "..."
uv run python -m burevestnik.main
```

Note: the local run will skip if the current Melbourne hour isn't in `{6, 9, 12, 15, 18}`. To force a post for testing, temporarily edit `POSTING_HOURS` in `src/burevestnik/main.py`.

## Re-capturing the test fixture

If meteoblue changes their layout and parse tests start failing:

```powershell
uv run python scripts/capture_fixture.py
uv run pytest    # update assertions in tests/test_parse.py if values changed
```
