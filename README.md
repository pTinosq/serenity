# Serenity

Your personal AI trader whose only strategy is to look at the most recent tweets from [Serenity's X account](https://x.com/aleabitoreddit) and make trades based on the content of the tweets.

## Requirements

- [`gum`](https://github.com/charmbracelet/gum#installation) — used for the interactive settings UI. Install via the link above (`brew install gum` on macOS).
- An **OpenRouter API key** — required to run the LLM stage. Grab one from <https://openrouter.ai/keys> and either set `OPENROUTER_API_KEY` in your `.env` or paste it into the **Settings** menu after running `serenity`. The model id lives in `SENTIMENT_MODEL` and uses OpenRouter's `provider/model` format (e.g. `openai/gpt-5.4-nano`); browse available models at <https://openrouter.ai/models>.
- An **X (Twitter) App Bearer Token** — required to ingest tweets. Create a project + app at <https://developer.x.com/en/portal/dashboard>, generate the **OAuth 2.0 App Bearer Token**, and set `X_BEARER_TOKEN` in your `.env` (or via the Settings menu). Tweets come from X's filtered stream (near-realtime, ~6s P99); the endpoint is pay-per-use ($0.005/post, capped at 2M/month — a few cents/month for a single account).

## Alerts

When the bot can't act on a signal (e.g. Alpaca rejects the ticker as non-tradeable), it surfaces an **alert** through the channel selected by `ALERT_FALLBACK_CHANNEL` (`stdout` | `telegram`, default `stdout`).

### Telegram setup

1. **Create a bot.** Open Telegram, search for `@BotFather`, run `/newbot`, follow the prompts. Copy the API token into `TELEGRAM_BOT_TOKEN` (in `.env` or via the Settings menu).
2. **DM your bot.** Send `/start` (or any message) so the bot has seen your chat.
3. **Find your chat ID.** Easiest path: search for `@userinfobot` on Telegram, hit Start, copy the numeric ID it replies with into `TELEGRAM_CHAT_ID`. Alternative: `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` and read `chat.id` out of the JSON.
4. **Flip the switch.** Set `ALERT_FALLBACK_CHANNEL=telegram` (env var or Settings menu).

Sanity-check the wiring without waiting for a real alert:

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"<CHAT_ID>","text":"serenity alerts wired ✅"}'
```

If telegram is selected but credentials are missing, the dispatcher logs a warning and falls back to stdout — alerts are never silently dropped.

## How it works

1. Listen for new tweets from Serenity
2. Use AI to understand what the tweet is suggesting about a stock
3. Make a trade based on the tweet
4. ???
5. Profit

## What you will look like in 2 days
<img width="192" height="237" alt="img" src="https://github.com/user-attachments/assets/6f468b6d-13d2-4545-a51b-fe50a30a9dbb" />
