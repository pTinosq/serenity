import logging

from serenity.logging_config import setup_logging

log = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    log.info("Hello from [bold cyan]serenity[/] :sparkles:")


if __name__ == "__main__":
    main()
