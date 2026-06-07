# Serenity

A sentiment-driven equities trading bot. Pulls tweets from a tracked X
account, has an LLM derive a structured trade signal from each tweet,
and executes the trade against Alpaca.

## Architecture

Three stages chained through narrow interfaces so each can be developed
and tested in isolation:

```
[Twitter] --tweet: str--> [LLM] --TradeSignal--> [Trading]
```

### 1. Twitter interface (`src/serenity/twitter.py`)

`stream_tweets(settings)` yields the body of each new tweet from
`TRACKED_X_ACCOUNT` as a `str`. Backed by X's filtered stream via
the official `xdk` SDK — push-based, near-realtime (~6s P99), with
SDK-managed auto-reconnect. On startup we wipe any leftover stream
rules from previous sessions (X stores rules server-side per app)
and install a fresh `from:<handle>` rule. The stream only delivers
tweets posted after the connection opens, so restarts don't replay
stale signal. The interface intentionally yields `str` so it
remains swappable with `input(":")` for offline dev.

### 2. Oracle (`src/serenity/oracle/`)

The middle stage. Implemented. `Oracle.analyze(text)` reads a piece of
text and returns a `TradeSignal`:

- `ticker: str` — ticker explicitly mentioned or very confidently
  inferred from a well-known company name. The string `"N/A"` is the
  abstention sentinel (no identifiable ticker).
- `order_type: Literal["BUY", "SELL", "N/A"]` — direction implied by
  sentiment, or `"N/A"` when the text doesn't give enough to act on
  (no ticker, observational text, hedged sentiment, or multiple
  tickers without a dominant subject). When `order_type == "N/A"`,
  `ticker` must also be `"N/A"`.
- `confidence: float` (0.0 – 1.0) — clarity of the signal in the
  text. Must be exactly `0.0` when `order_type == "N/A"`.

The system prompt lives at `oracle/prompt.md` and is loaded via
`Path(__file__).parent / "prompt.md"`. The OpenRouter client is a
process-wide singleton via `functools.lru_cache(maxsize=1)`. Model id
is configurable via `SENTIMENT_MODEL` and uses OpenRouter's
`provider/model` format (e.g. `google/gemini-2.5-flash`). Structured
output is enforced via `response_format={"type": "json_schema", ...}`
with `strict: true` and the schema is derived from `TradeSignal`.

An interactive REPL at `src/serenity/cli/analyze.py` (`just oracle`)
lets you type free-text and see the TradeSignal output.

### 3. Trading interface (`src/serenity/trading.py`)

`execute_trade(signal, settings)` turns a `TradeSignal` into a market
order via `alpaca-py`. Submits a `MarketOrderRequest` sized by
sentiment magnitude:

```
notional = clamp(signal.sentiment * MAX_TRADE_USD, MIN_TRADE_USD, MAX_TRADE_USD)
notional = min(notional, available_cash)
```

So weaker calls cost less and the bot doesn't blow its budget on the
first hot signal. `confidence` remains the *gate* (sub-`MIN_CONFIDENCE`
trades are skipped); `sentiment` is the *sizer*. Returns a
`TradeOutcome` enum:

- `EXECUTED` — order submitted.
- `SKIPPED_NO_SIGNAL` — `order_type == "N/A"`.
- `SKIPPED_LOW_CONFIDENCE` — `confidence < MIN_CONFIDENCE`.
- `SKIPPED_BELOW_MIN_TRADE` — sized below `MIN_TRADE_USD`.
- `SKIPPED_PRICE_TOO_HIGH` — opening a short but one share costs more than the sized notional (see below).
- `SKIPPED_NOT_TRADEABLE` — Alpaca returned 40010001 ("asset not active" / "not found"). Most often the Oracle extracted a foreign-listed ticker that happened to be cashtagged like a US one (e.g. `$SIVE` is Sivers Semiconductors on Nasdaq Stockholm).
- `SKIPPED_NO_CASH` — Alpaca cash balance below `MIN_TRADE_USD`.
- `SKIPPED_NO_CREDENTIALS` — Alpaca keys not set; rest of pipeline runs.
- `SKIPPED_SHORTS_DISABLED` — SELL signal on a ticker we don't currently hold, and `ALLOW_SHORTS` is False. See below.
- `FAILED` — reserved; Alpaca errors raise `TradingError` instead.

Alpaca disallows fractional shorts: submitting a SELL with `notional`
on a ticker we don't hold returns `42210000`. We catch that, fetch
the last trade price via `StockHistoricalDataClient`, recompute as
`qty = floor(notional / price)`, and retry. If `qty < 1` (stock
costs more than the sized notional), the trade is skipped with
`SKIPPED_PRICE_TOO_HIGH`. Closing-long SELLs on tickers we hold are
not affected and continue to use fractional notional.

`ALLOW_SHORTS` defaults to `False`. In this mode a SELL signal is treated
as "close some of the existing long", not "open a new short". If the
ticker isn't already held, the trade is skipped with
`SKIPPED_SHORTS_DISABLED` and an alert fires so the user can act manually
if they want exposure. Flip `ALLOW_SHORTS=True` to restore the old
behaviour where SELLs on un-held tickers open whole-share shorts.

`ALPACA_PAPER` defaults to `True`, so the default install is safe.
The `TradingClient` is a process-wide singleton via
`functools.lru_cache(maxsize=1)`, same pattern as the Oracle client.

## Settings

All config lives in `src/serenity/config.py` via `pydantic-settings`
(env + `.env`). `.env.example` is the source of truth for the full
list. Required values (`OPENROUTER_API_KEY`, `TRACKED_X_ACCOUNT`,
`X_BEARER_TOKEN`) fail loudly at startup if missing. Alpaca keys
(`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`) are optional — if absent, the
Twitter→Oracle pipeline still runs and `execute_trade` returns
`SKIPPED_NO_CREDENTIALS`.

Users can edit settings interactively via the `Settings` entry of the
main menu (see below). Edits are validated per-field with a pydantic
`TypeAdapter` and written back to `.env` via `python-dotenv`'s
`set_key`.

## Alerts

`src/serenity/alerts/` is a modular notification layer for things the
bot couldn't act on but the user might want to act on manually (a
strong signal on a non-US ticker, etc.). One file per channel.
Currently shipped:

- `stdout.py` — rich panel printed to the terminal.
- `telegram.py` — message via the Telegram Bot API
  (`sendMessage`, HTML parse mode, stdlib `urllib`).

Channel selection is single-pick via `ALERT_FALLBACK_CHANNEL`
(`stdout` | `telegram`, default `stdout`). The dispatcher reads the
setting on each `dispatch()` call and routes to the selected channel.
If `telegram` is selected but `TELEGRAM_BOT_TOKEN` /
`TELEGRAM_CHAT_ID` are unset, the dispatcher logs a warning and falls
back to stdout — alerts are never silently dropped. Per-channel
exceptions are caught so a broken channel can't crash the trading
loop.

Call site:

```python
from serenity.alerts import Alert, dispatch
dispatch(Alert(reason="not_tradeable", title=..., signal=signal, detail=...))
```

The dispatcher swallows per-channel errors so a broken telegram bot
won't silence stdout.

### Message frequency

`MESSAGE_FREQUENCY` controls delivery cadence:

- `per-tweet` (default) — every `Messenger.send(Alert(...))` is
  delivered immediately. Noisy when the tracked account tweets a lot.
- `daily` — `Alert` payloads are appended to a persistent JSONL
  buffer at `data/event_log.jsonl`. A daemon scheduler thread
  (`alerts/scheduler.py`) wakes once per day at
  `DAILY_MESSAGE_DELIVERY_UTC` (HH:MM UTC, default `21:30`), calls
  `flush_daily_summary()`, which drains the buffer and asks the
  active channel to `render_summary(events)`. Channels own their own
  summary format (Stdout uses a Rich panel; Telegram uses uppercase
  reason headers + bulleted lines).

Out-of-band messages bypass the buffer even in daily mode:
plain-string `dispatch("...")` calls go straight to the channel,
and `notify_crash()` passes `force=True` so a fatal error message
ships immediately rather than waiting until the next slot.

The JSONL buffer is crash-resilient: Railway redeploys mid-day
don't drop events. The fresh instance picks up the existing log and
the scheduler delivers normally.

## Entry points

`serenity` (no args) opens an interactive menu (Start / Settings /
Exit), rendered via [gum](https://github.com/charmbracelet/gum). gum is
a runtime prerequisite, not a Python dep — see the README.

Pass `--headless` to skip the menu and go straight to the bot loop.
`just dev` and `just start-headless` use `--headless`; `just start`
opens the menu.

User-facing UI components (gum wrapper, main menu, settings editor)
live in `src/serenity/ui/`. `src/serenity/cli/` is reserved for
developer scripts: the Oracle REPL (`cli/analyze.py`, `just oracle`)
and the interactive `.env` wizard (`cli/init.py`, `just init`). The
wizard reuses `ui/settings.py`'s `prompt_new_value`/`validate` so
dropdowns and per-field validation come for free.

## Evals

`evals/` holds a dev-only eval harness, separate from the product.
`evals/dataset.json` is a list of `{tweet, result}` cases; `result`
specifies the expected ticker, order_type, and confidence conditions
(`gt` / `lt` / `eq`, combined with AND). `just eval` runs each case
through the Oracle and prints per-case marks plus a summary with
per-dimension accuracy and a weighted score (ticker 0.4, order 0.5,
confidence 0.1). The "Order | correct ticker" row in the summary
surfaces the cascading nature of these dimensions — a trade with the
right action but the wrong ticker is still useless.

## Conventions

- **Always** use `uv add` / `uv add --dev` for dependencies — never
  hand-edit `pyproject.toml`. LLMs don't know current latest versions;
  `uv add` resolves them correctly.
- `just dev` runs with `watchfiles` auto-reload; `just start` is prod.
  Both auto-load `.env` (`set dotenv-load := true`).
- Single console-script entry point: `serenity = "serenity.main:main"`.
- src-layout package under `src/serenity/`.

## Workflow

All code changes ship via pull requests, never direct commits to `main`:

1. Make the requested changes on a feature branch.
2. Commit incrementally as you go — multiple small, logically scoped
   commits, not one big dump at the end. Each commit should stand on
   its own (one concern per commit).
3. When the change is complete, push the branch and open a PR.
4. **Never merge a PR.** The user reviews and merges; they may iterate
   with you on the branch first. Do not run `gh pr merge` even if the
   PR looks ready.
