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

### 1. Twitter interface (`src/serenity/twitter.py`, not yet implemented)

Streams the most recent tweets from a tracked X account. The X API is
expensive, so the production implementation will most likely be a
scraper — that decision is unresolved. The interface only ever yields
a tweet body as a `str`, which means during development the test
harness can substitute `input(":")` and the rest of the pipeline still
works. This stage is implemented **last**.

### 2. Oracle (`src/serenity/oracle/`)

The middle stage. Implemented. `Oracle.analyze(text)` reads a piece of
text and returns a `TradeSignal`:

- `ticker: str | None` — ticker explicitly mentioned in the text; None
  if no ticker is named (no inference is allowed).
- `order_type: Literal["BUY", "SELL"] | None` — direction implied by
  sentiment. None when there is no actionable signal.
- `confidence: float` (0.0 – 1.0) — clarity of the signal in the text.

The system prompt lives at `oracle/prompt.md` and is loaded via
`Path(__file__).parent / "prompt.md"`. The OpenAI client is a
process-wide singleton via `functools.lru_cache(maxsize=1)`. Model id
is configurable via `SENTIMENT_MODEL`.

An interactive REPL at `src/serenity/cli/analyze.py` (`just oracle`)
lets you type free-text and see the TradeSignal output.

### 3. Trading interface (`src/serenity/trading.py`, not yet implemented)

Executes the `TradeSignal` via `alpaca-py` (install with
`uv add alpaca-py` when we start — deliberately not added yet).
Bare-bones for now; the goal is just to learn the SDK well enough to
turn a `TradeSignal` into an order. Orders are skipped if
`confidence < MIN_CONFIDENCE` or implied notional exceeds
`MAX_ORDER_AMOUNT_USD`.

## Settings

All config lives in `src/serenity/config.py` via `pydantic-settings`
(env + `.env`). `.env.example` is the source of truth for the full
list. Required values (`OPENAI_API_KEY`, `TRACKED_X_ACCOUNT`) fail
loudly at startup if missing.

Users can edit settings interactively via the `Settings` entry of the
main menu (see below). Edits are validated per-field with a pydantic
`TypeAdapter` and written back to `.env` via `python-dotenv`'s
`set_key`.

## Entry points

`serenity` (no args) opens an interactive menu (Start / Settings /
Exit), rendered via [gum](https://github.com/charmbracelet/gum). gum is
a runtime prerequisite, not a Python dep — see the README.

Pass `--headless` to skip the menu and go straight to the bot loop.
`just dev` and `just start-headless` use `--headless`; `just start`
opens the menu.

User-facing UI components (gum wrapper, main menu, settings editor)
live in `src/serenity/ui/`. `src/serenity/cli/` is reserved for
developer scripts (e.g. the Oracle REPL at `cli/analyze.py`).

## Conventions

- **Always** use `uv add` / `uv add --dev` for dependencies — never
  hand-edit `pyproject.toml`. LLMs don't know current latest versions;
  `uv add` resolves them correctly.
- `just dev` runs with `watchfiles` auto-reload; `just start` is prod.
  Both auto-load `.env` (`set dotenv-load := true`).
- Single console-script entry point: `serenity = "serenity.main:main"`.
- src-layout package under `src/serenity/`.
