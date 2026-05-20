set dotenv-load := true

default:
    @just --list

# Run in dev mode with auto-reload on file changes
dev:
    uv run watchfiles "serenity" src

# Run in production mode
start:
    uv run serenity

# Install / sync dependencies
install:
    uv sync

# Run the Oracle REPL (interactive LLM signal extractor)
oracle:
    uv run python -m serenity.cli.analyze

# Type-check / lint stubs (extend later)
fmt:
    uv run ruff format src
