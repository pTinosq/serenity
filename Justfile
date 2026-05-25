set dotenv-load := true

default:
    @just --list

# Run in dev mode with auto-reload on file changes (skips the interactive menu)
dev:
    uv run watchfiles "serenity" src

# Run in production mode (skips the interactive menu)
start-headless:
    uv run serenity --headless

# Open the interactive menu (Start / Settings / Exit)
start:
    uv run serenity

# Install / sync dependencies
install:
    uv sync

# Interactive .env wizard — walks you through the minimum config
init:
    uv run python -m serenity.cli.init

# Run the Oracle REPL (interactive LLM signal extractor)
oracle:
    uv run python -m serenity.cli.analyze

# Run the Oracle against the dev eval dataset (evals/dataset.json)
eval:
    uv run python evals/run.py

# Type-check / lint stubs (extend later)
fmt:
    uv run ruff format src
