"""Stdout alert channel — a rich-formatted panel for terminal sessions."""

from __future__ import annotations

from rich import print as rprint
from rich.panel import Panel

from serenity.alerts.base import Alert


class StdoutChannel:
    name = "stdout"

    def send(self, alert: Alert) -> None:
        sig = alert.signal
        lines = [
            f"[bold]{alert.title}[/]",
            "",
            f"[cyan]{sig.order_type} {sig.ticker}[/]  "
            f"conf {sig.confidence:.2f}  sent {sig.sentiment:.2f}",
        ]
        if alert.detail:
            lines.append("")
            lines.append(f"[dim]{alert.detail}[/]")
        rprint(
            Panel(
                "\n".join(lines),
                title=f"⚠ alert: {alert.reason}",
                border_style="yellow",
            )
        )
