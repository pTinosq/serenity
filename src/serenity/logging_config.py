import logging

from rich.logging import RichHandler

from serenity.config import LogLevel


def setup_logging(level: LogLevel) -> None:
    logging.basicConfig(
        level=level,
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
