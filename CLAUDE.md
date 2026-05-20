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

### 2. LLM interface (`src/serenity/llm.py`, not yet implemented)

Input: tweet `str`. Output: a Pydantic `TradeSignal` derived via
OpenAI's structured output, with fields roughly:

- `ticker: str`
- `order_type: Literal["BUY", "SELL"]`
- `confidence: float` (0.0 – 1.0)

The system prompt that grounds the model lives alongside this module.
Model id is configurable via `SENTIMENT_MODEL`.

### 3. Trading interface (`src/serenity/trading.py`, not yet implemented)

Executes the `TradeSignal` via `alpaca-py` (install with
`uv add alpaca-py` when we start — deliberately not added yet).
Bare-bones for now; the goal is just to learn the SDK well enough to
turn a `TradeSignal` into an order. Orders are skipped if
`confidence < MIN_CONFIDENCE` or implied notional exceeds
`MAX_ORDER_AMOUNT`.

## Settings

All config lives in `src/serenity/config.py` via `pydantic-settings`
(env + `.env`). `.env.example` is the source of truth for the full
list. Required values (`OPENAI_API_KEY`, `TRACKED_X_ACCOUNT`) fail
loudly at startup if missing.

## Conventions

- **Always** use `uv add` / `uv add --dev` for dependencies — never
  hand-edit `pyproject.toml`. LLMs don't know current latest versions;
  `uv add` resolves them correctly.
- `just dev` runs with `watchfiles` auto-reload; `just start` is prod.
  Both auto-load `.env` (`set dotenv-load := true`).
- Single console-script entry point: `serenity = "serenity.main:main"`.
- src-layout package under `src/serenity/`.
