"""Stdout alert channel — a rich-formatted panel for terminal sessions."""

from __future__ import annotations

from rich import print as rprint
from rich.markup import escape
from rich.panel import Panel


class StdoutChannel:
    name = "stdout"

    def send(self, text: str) -> None:
        rprint(Panel(escape(text), border_style="yellow"))
