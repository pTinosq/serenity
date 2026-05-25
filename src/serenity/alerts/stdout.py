"""Stdout alert channel — a rich-formatted panel for terminal sessions."""

from __future__ import annotations

from collections import defaultdict

from rich import print as rprint
from rich.markup import escape
from rich.panel import Panel

from serenity.alerts.event_log import Event


class StdoutChannel:
    name = "stdout"

    def send(self, text: str) -> None:
        rprint(Panel(escape(text), border_style="yellow"))

    def render_summary(self, events: list[Event]) -> str:
        if not events:
            return "Daily summary — no events to report."

        day = events[0].timestamp.strftime("%Y-%m-%d")
        header = f"Daily summary — {day}\n{len(events)} event(s)"

        groups: dict[str, list[Event]] = defaultdict(list)
        for e in events:
            groups[e.alert.reason].append(e)

        sections = []
        for reason, items in groups.items():
            lines = [f"\n[{reason}] {len(items)}"]
            for e in items:
                t = e.timestamp.strftime("%H:%M UTC")
                lines.append(f"  {t}  {e.alert.title}")
            sections.append("\n".join(lines))

        return header + "\n" + "\n".join(sections)
