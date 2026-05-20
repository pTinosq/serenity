import logging

from serenity.config import load_settings
from serenity.logging_config import setup_logging

log = logging.getLogger(__name__)


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    log.info("Hello from [bold cyan]serenity[/] :sparkles:")
    log.debug("Loaded settings: %s", settings.model_dump())


if __name__ == "__main__":
    main()
