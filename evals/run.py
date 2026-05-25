"""Run the Oracle against the dev eval dataset and report scores.

Usage: `just eval` (or `uv run python evals/run.py`). The dataset lives
at `evals/dataset.json` and is shaped as a list of:

    {
      "tweet": "...",
      "result": {
        "ticker": "NVDA" | "N/A",
        "order_type": "BUY" | "SELL" | "N/A",
        "confidence": {"gte": 0.7, "lte": 1.0, "eq": null}
      }
    }

Each `confidence` condition is optional and they combine with AND. The
score for a case is a weighted sum of three checks; weights live in the
constants at the top of this file. Per-dimension accuracy is reported
alongside, so the "critical" dimensions (ticker, order) show up even
when the weighted score looks healthy.

Pass --quiet to suppress the banner, per-case progress prints, and the
verbose per-case table. Quiet mode prints only the summary plus a
compact failures list — suitable for an LLM consumer reading the
output without burning tokens on noise.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from serenity.config import load_settings
from serenity.logging_config import setup_logging
from serenity.oracle import Oracle, TradeSignal

DATASET_PATH = Path(__file__).parent / "dataset.json"

WEIGHT_TICKER = 0.4
WEIGHT_ORDER = 0.5
WEIGHT_CONFIDENCE = 0.1


class ConfidenceCondition(BaseModel):
    gte: float | None = None
    lte: float | None = None
    eq: float | None = None

    def matches(self, actual: float) -> bool:
        if self.gte is not None and not actual >= self.gte:
            return False
        if self.lte is not None and not actual <= self.lte:
            return False
        if self.eq is not None and actual != self.eq:
            return False
        return True

    def describe(self) -> str:
        parts = []
        if self.gte is not None:
            parts.append(f"gte {self.gte}")
        if self.lte is not None:
            parts.append(f"lte {self.lte}")
        if self.eq is not None:
            parts.append(f"eq {self.eq}")
        return " & ".join(parts) if parts else "any"


class ExpectedResult(BaseModel):
    ticker: str
    order_type: Literal["BUY", "SELL", "N/A"]
    confidence: ConfidenceCondition = ConfidenceCondition()


class EvalCase(BaseModel):
    tweet: str
    result: ExpectedResult


class CaseOutcome(BaseModel):
    case: EvalCase
    signal: TradeSignal | None = None
    error: str | None = None
    ticker_ok: bool = False
    order_ok: bool = False
    conf_ok: bool = False
    weighted: float = 0.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="evals/run.py")
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help=(
            "Suppress progress prints and the verbose per-case table. "
            "Print only the summary plus a compact failures list."
        ),
    )
    return parser.parse_args(argv)


def load_dataset() -> list[EvalCase]:
    raw = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    return [EvalCase.model_validate(c) for c in raw]


def evaluate_case(case: EvalCase, oracle: Oracle) -> CaseOutcome:
    try:
        signal = oracle.analyze(case.tweet)
    except Exception as e:
        return CaseOutcome(case=case, error=str(e))

    expected_ticker = (case.result.ticker or "").upper()
    actual_ticker = (signal.ticker or "").upper()
    ticker_ok = expected_ticker == actual_ticker

    order_ok = signal.order_type == case.result.order_type
    conf_ok = case.result.confidence.matches(signal.confidence)

    weighted = (
        WEIGHT_TICKER * ticker_ok
        + WEIGHT_ORDER * order_ok
        + WEIGHT_CONFIDENCE * conf_ok
    )

    return CaseOutcome(
        case=case,
        signal=signal,
        ticker_ok=ticker_ok,
        order_ok=order_ok,
        conf_ok=conf_ok,
        weighted=weighted,
    )


def render_results(outcomes: list[CaseOutcome], console: Console) -> None:
    table = Table(title=f"Cases — {DATASET_PATH.name}")
    table.add_column("#", justify="right")
    table.add_column("Tweet", overflow="fold", max_width=60)
    table.add_column("T", justify="center")
    table.add_column("O", justify="center")
    table.add_column("C", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Got")

    mark = {True: "[green]✓[/]", False: "[red]✗[/]"}
    for i, o in enumerate(outcomes, 1):
        if o.error or o.signal is None:
            table.add_row(
                str(i),
                o.case.tweet,
                "—",
                "—",
                "—",
                "—",
                f"[red]ERROR:[/] {(o.error or '')[:60]}",
            )
            continue
        got = (
            f"{o.signal.ticker or '∅'} / "
            f"{o.signal.order_type or '∅'} / "
            f"{o.signal.confidence:.2f}"
        )
        table.add_row(
            str(i),
            o.case.tweet,
            mark[o.ticker_ok],
            mark[o.order_ok],
            mark[o.conf_ok],
            f"{o.weighted:.2f}",
            got,
        )
    console.print(table)


def render_summary(outcomes: list[CaseOutcome], console: Console) -> None:
    n = len(outcomes)
    valid = [o for o in outcomes if o.error is None]
    if not valid:
        console.print("[red]All cases errored.[/]")
        return

    ticker_acc = sum(o.ticker_ok for o in valid) / n
    order_acc = sum(o.order_ok for o in valid) / n
    conf_acc = sum(o.conf_ok for o in valid) / n
    overall = sum(o.weighted for o in valid) / n

    correct_t = [o for o in valid if o.ticker_ok]
    order_given_ticker = (
        sum(o.order_ok for o in correct_t) / len(correct_t) if correct_t else 0.0
    )

    table = Table(title="Summary", show_header=False)
    table.add_column()
    table.add_column(justify="right")
    table.add_row("Cases", str(n))
    if n - len(valid):
        table.add_row("Errored", str(n - len(valid)))
    table.add_row("Ticker accuracy", f"{ticker_acc:.1%}")
    table.add_row("Order accuracy", f"{order_acc:.1%}")
    table.add_row("Confidence accuracy", f"{conf_acc:.1%}")
    table.add_row("Order | correct ticker", f"{order_given_ticker:.1%}")
    table.add_row(
        "Weighted score",
        f"[bold]{overall:.1%}[/]   "
        f"(T={WEIGHT_TICKER}, O={WEIGHT_ORDER}, C={WEIGHT_CONFIDENCE})",
    )
    console.print(table)


def render_failures(outcomes: list[CaseOutcome], console: Console) -> None:
    """Compact per-failure breakdown: what was expected vs what was got, per dimension."""
    failures = [
        (i, o)
        for i, o in enumerate(outcomes, 1)
        if o.error or not (o.ticker_ok and o.order_ok and o.conf_ok)
    ]
    if not failures:
        console.print("\n[green]No failures.[/]")
        return

    console.print(f"\n[bold]Failures ({len(failures)}):[/]")
    for i, o in failures:
        snippet = o.case.tweet.replace("\n", " ").strip()[:60]
        snippet += "…" if len(o.case.tweet) > 60 else ""
        if o.error or o.signal is None:
            console.print(f"  [{i}] ERROR: {(o.error or '')[:80]}  — \"{snippet}\"")
            continue
        reasons: list[str] = []
        if not o.ticker_ok:
            reasons.append(
                f"ticker expected {o.case.result.ticker!r}, got {o.signal.ticker!r}"
            )
        if not o.order_ok:
            reasons.append(
                f"order expected {o.case.result.order_type}, got {o.signal.order_type}"
            )
        if not o.conf_ok:
            reasons.append(
                f"confidence expected {o.case.result.confidence.describe()}, "
                f"got {o.signal.confidence:.2f}"
            )
        console.print(f"  [{i}] {'; '.join(reasons)}  — \"{snippet}\"")


def main() -> None:
    args = parse_args(sys.argv[1:])
    settings = load_settings()
    setup_logging(settings.log_level)

    cases = load_dataset()
    oracle = Oracle(settings=settings)

    console = Console()
    if not args.quiet:
        console.print(
            f"Running [bold]{len(cases)}[/] case(s) through "
            f"[bold cyan]{settings.sentiment_model}[/]...\n"
        )

    outcomes: list[CaseOutcome] = []
    for i, case in enumerate(cases, 1):
        if not args.quiet:
            preview = case.tweet[:80] + ("..." if len(case.tweet) > 80 else "")
            console.print(f"  [{i}/{len(cases)}] {preview}")
        outcomes.append(evaluate_case(case, oracle))

    if not args.quiet:
        console.print()
        render_results(outcomes, console)

    render_summary(outcomes, console)
    render_failures(outcomes, console)


if __name__ == "__main__":
    main()
