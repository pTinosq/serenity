"""Thin subprocess wrapper around the `gum` CLI.

gum (https://github.com/charmbracelet/gum) renders the interactive
menu and settings editor. This module hides the subprocess plumbing
behind a few functions and translates user-cancel (non-zero exit) into
KeyboardInterrupt so callers can use a single except clause.
"""

import shutil
import subprocess


class GumNotInstalled(RuntimeError):
    """Raised when the `gum` binary cannot be found on PATH."""


def require_gum() -> None:
    if shutil.which("gum") is None:
        raise GumNotInstalled(
            "gum is required for the interactive UI. "
            "Install it from https://github.com/charmbracelet/gum#installation "
            "(e.g. `brew install gum` on macOS)."
        )


def run_gum(args: list[str]) -> str:
    require_gum()
    result = subprocess.run(args, stdout=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise KeyboardInterrupt
    return result.stdout.strip("\n")


def choose(
    *options: str,
    header: str | None = None,
    selected: str | None = None,
) -> str:
    """Show a vertical chooser; return the selected option as a string."""
    args = ["gum", "choose"]
    if header:
        args += ["--header", header]
    if selected:
        args += ["--selected", selected]
    args += list(options)
    return run_gum(args)


def ask(
    *,
    prompt: str = "> ",
    value: str = "",
    placeholder: str = "",
    password: bool = False,
) -> str:
    """Prompt for a single line; return what the user typed."""
    args = ["gum", "input", "--prompt", prompt]
    if value:
        args += ["--value", value]
    if placeholder:
        args += ["--placeholder", placeholder]
    if password:
        args += ["--password"]
    return run_gum(args)


def confirm(prompt: str) -> bool:
    """Yes/no prompt; True if the user confirmed."""
    require_gum()
    result = subprocess.run(["gum", "confirm", prompt])
    return result.returncode == 0


def style(text: str, *, foreground: str | None = None, bold: bool = False) -> None:
    """Print a styled line via `gum style`."""
    require_gum()
    args = ["gum", "style"]
    if foreground:
        args += ["--foreground", foreground]
    if bold:
        args += ["--bold"]
    args += [text]
    subprocess.run(args)
