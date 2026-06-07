# Serenity

A sentiment-driven equities trading bot. Pulls tweets from a tracked X
account, has an LLM derive a structured trade signal from each tweet,
and executes the trade against Alpaca.

## Architecture

Four stages, two of them LLM agents, chained through narrow interfaces:

```
[Twitter] --tweet--> [Oracle] --TradeSignal--> [TradeExecutor] --TradePlan--> [Runner]
                       agent                       agent                   submits orders
```

Both agents inherit from the shared harness in `src/serenity/agents/`.
Adding a new agent is one OOP instantiation: a class with `name`,
`output_model`, and `prompt_path`, plus whatever domain-specific
method composes the user message.

### 0. Agent harness (`src/serenity/agents/`)

`Agent[OutputT]` (generic in the Pydantic output type) owns the
OpenRouter wiring: a process-wide cached `OpenRouter` client, the
system prompt loaded from `prompt_path`, the response schema derived
from `output_model` and recursively locked with
`additionalProperties: false` (strict JSON-schema mode needs this on
every nested object, not just the root), and the parse step that
turns the model's content back into a Pydantic instance. Subclasses
typically wrap `self.run(user_message)` with a domain-named method
(`Oracle.analyze`, `TradeExecutor.decide`) so callers don't see the
raw string transport.

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

A thin `Agent[TradeSignal]` subclass. `Oracle.analyze(text)` reads a
piece of text and returns a `TradeSignal`:

- `ticker: str` — ticker explicitly mentioned or very confidently
  inferred from a well-known company name. `"N/A"` is the abstention
  sentinel (no identifiable ticker).
- `order_type: Literal["BUY", "SELL", "N/A"]` — direction implied by
  sentiment, or `"N/A"` when the text doesn't give enough to act on.
  When `order_type == "N/A"`, `ticker` must also be `"N/A"`.
- `confidence: float` (0.0 – 1.0) — clarity of the signal in the
  text. `0.0` exactly when `order_type == "N/A"`.
- `sentiment: float` (0.0 – 1.0) — conviction magnitude. Distinct from
  confidence; `0.0` exactly when `order_type == "N/A"`.

The Oracle's job ends here. It does **not** decide how much to trade
or whether to trade at all — that's the executor's job, with full
portfolio context the Oracle never sees.

System prompt at `oracle/prompt.md`. Model id is `SENTIMENT_MODEL`
(default `google/gemini-2.5-flash`); shared with the executor.

Interactive REPL at `src/serenity/cli/analyze.py` (`just oracle`)
shows both the Oracle signal and (if Alpaca creds are set) the
executor's plan, gated on a confirm before submitting.

### 3. TradeExecutor (`src/serenity/executor/`)

The second agent, also an `Agent` subclass — output type `TradePlan`.
Per tweet, `TradeExecutor.decide(tweet, signal, positions, available_cash)`
sees:

- the original tweet text (for nuance the Oracle compressed away)
- the Oracle's structured signal
- the current portfolio (each position with cost basis, market value,
  unrealized P&L, and portfolio_fraction)
- available cash for new trades
- the configured risk bounds (`MIN_TRADE_USD`, `MAX_TRADE_USD`,
  `MAX_POSITION_USD`)

and returns a `TradePlan` — a list of `TradeAction`s (`BUY` notional,
`TRIM` fraction, `CLOSE`, or `HOLD`) plus a one-sentence summary. The
plan can be empty; that's a valid answer.

The prompt at `executor/prompt.md` encodes the policy: BUY when no
existing position; top-up at half-size on high-conviction reinforce;
CLOSE long positions on high-conviction SELL; do nothing if cash is
too low (don't try to clever-rebalance by closing other names).

### 4. Runner (`src/serenity/executor/runner.py`)

`apply_plan(client, settings, plan, available_cash)` is the bridge
from `TradePlan` to actual Alpaca orders, with hard safety guards
that don't trust the LLM:

- `MAX_TRADES_PER_DAY` cap (counts every order Alpaca has seen on
  this account since UTC midnight). If hit, the whole plan is
  skipped with `Outcome.SKIPPED_DAILY_CAP`.
- For BUY: existing position value is fetched; the action is sized
  down to fit the `MAX_POSITION_USD` headroom, capped at remaining
  cash, capped at `MAX_TRADE_USD`. If headroom < `MIN_TRADE_USD`, skip
  with `SKIPPED_POSITION_CAP`.
- For TRIM/CLOSE: requires an existing position; otherwise
  `SKIPPED_NO_POSITION`. Submits via `close_position(..., percentage)`
  for TRIM and `close_position(...)` for CLOSE (the endpoint is
  symmetric across long/short).
- Individual action failures don't stop later actions — partial
  application beats silent drops.

`src/serenity/trading.py` is now a small infrastructure module:
cached `TradingClient` builder + the `size_trade` sentiment-to-notional
helper (kept as the canonical default-sizing formula, used by tests
and exposed for callers that want it).

### Portfolio snapshot (`src/serenity/portfolio/`)

Single-file module: one model (`PortfolioPosition`), one function
(`fetch_portfolio(client)`). Reads open positions from Alpaca and
pre-computes each row's `portfolio_fraction` so the executor agent
can reason about concentration without a second pass over the data.

`ALPACA_PAPER` defaults to `True`, so the default install is safe.

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
- **Never** write `from __future__ import annotations`. This project
  targets Python 3.12+ (`pyproject.toml` pins `>=3.12`); the future
  import does nothing on modern Python and is just noise. Modern
  union syntax (`X | None`), built-in generics (`list[str]`), and
  string-quoted forward references all work natively.

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
