set dotenv-load := true

default:
    @just --list

# Run in dev mode with auto-reload on file changes
dev:
    uv run watchfiles "python -m serenity" src

# Run in production mode
start:
    uv run python -m serenity

# Install / sync dependencies
install:
    uv sync

# Type-check / lint stubs (extend later)
fmt:
    uv run ruff format src
