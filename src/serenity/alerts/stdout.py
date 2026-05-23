"""Stdout alert channel — a rich-formatted panel for terminal sessions."""

from __future__ import annotations

from rich import print as rprint
from rich.panel import Panel

from serenity.alerts.base import Alert


class StdoutChannel:
    name = "stdout"

    def send(self, alert: Alert) -> None:
        sig = alert.signal
        headline = f"[cyan]{sig.order_type} {sig.ticker}[/]"
        if alert.amount is not None:
            headline += f"  [green]${alert.amount:.2f}[/]"
        headline += f"  conf {sig.confidence:.2f}  sent {sig.sentiment:.2f}"
        lines = [
            f"[bold]{alert.title}[/]",
            "",
            headline,
        ]
        if alert.tweet:
            lines.append("")
            lines.append(f"[dim italic]“{alert.tweet}”[/]")
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
