import logging
import os

from rich.logging import RichHandler


def setup_logging(level: str | None = None) -> None:
    log_level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()

    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                markup=True,
                show_path=False,
            )
        ],
    )
