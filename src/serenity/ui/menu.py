"""Top-level interactive menu shown when serenity is run without --headless."""

from typing import Callable

from serenity.ui import gum
from serenity.ui.settings import open_settings

START = "Start"
REVIEW_PORTFOLIO = "Review portfolio"
SETTINGS = "Settings"
EXIT = "Exit"
OPTIONS = [START, REVIEW_PORTFOLIO, SETTINGS, EXIT]


def run_menu(on_start: Callable[[], None]) -> None:
    """Show the main menu in a loop until the user picks Start or Exit.

    `on_start` is invoked when the user picks Start, keeping this module
    decoupled from the bot loop.
    """
    while True:
        try:
            choice = gum.choose(*OPTIONS, header="Serenity")
        except KeyboardInterrupt:
            return

        if choice == START:
            on_start()
            return
        if choice == REVIEW_PORTFOLIO:
            from serenity.cli.portfolio import main as review_portfolio
            review_portfolio()
            continue
        if choice == SETTINGS:
            open_settings()
            continue
        return
