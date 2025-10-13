from __future__ import annotations

import json
import textwrap
from contextlib import contextmanager
from typing import Any

import typer

# ====== Default configuration =====================================================

_DEFAULT_WIDTH = 72
_LABEL_ALIGN = 22  # reserved width for labels in kv()


# ====== Styling utilities =========================================================


def _color_for(level: str | None):
    """Return the color associated with a given log level."""
    mapping = {
        "info": typer.colors.BLUE,
        "ok": typer.colors.GREEN,
        "warn": typer.colors.YELLOW,
        "error": typer.colors.RED,
        "muted": typer.colors.WHITE,
    }
    return mapping.get(level or "", None)


def _stringify(value: Any) -> str:
    """Convert a value into a string representation.

    - `None` → empty string
    - `dict` or `list` → pretty JSON string
    - Other values → `str(value)`
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, indent=2, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


# ====== Display primitives ========================================================


def hr(*, width: int = _DEFAULT_WIDTH, char: str = "─", dim: bool = True) -> None:
    """Print a horizontal rule."""
    line = char * max(8, width)
    typer.echo(typer.style(line, dim=dim))


def section(title: str, *, width: int = _DEFAULT_WIDTH) -> None:
    """Print a titled section with a horizontal rule above and below."""
    hr(width=width)
    typer.echo(typer.style(f" {title}", bold=True))
    hr(width=width)


@contextmanager
def section_cm(title: str, *, width: int = _DEFAULT_WIDTH):
    """Context manager to open a titled section.

    Prints a header before entering the block and a closing horizontal rule on exit.
    """
    section(title, width=width)
    try:
        yield
    finally:
        hr(width=width)


def kv(
    label: str,
    value: Any,
    *,
    color: str | None = None,
    level: str | None = None,
    align: int = _LABEL_ALIGN,
    width: int = _DEFAULT_WIDTH,
    wrap: bool = False,
) -> None:
    """Display a key–value pair with proper alignment.

    Args:
        label: The key/label text.
        value: The value to display.
        color: Explicit color (e.g., `typer.colors.RED`).
            Takes precedence over `level`.
        level: Semantic level (`"info" | "ok" | "warn" | "error"`).
            Mapped to a consistent color palette.
        align: Minimum alignment width for labels.
        width: Maximum line width.
        wrap: If True, long values will be wrapped across multiple lines.

    Notes:
        - Values equal to `"unknown"` (case-insensitive) or empty are skipped.
        - Multiline values are indented consistently under the label.
    """
    if value is None:
        return

    label_txt = typer.style(f"{label}:", bold=True)
    pad = " " * max(1, align - len(label) - 1)

    text = _stringify(value).strip()
    if not text or text.lower() == "unknown":
        return

    val_color = color or _color_for(level)
    if wrap and "\n" not in text:
        # Soft wrapping while keeping alignment
        avail = max(10, width - align)
        wrapped = textwrap.wrap(text, width=avail) or [text]
        first = wrapped[0]
        rest = wrapped[1:]
        first_txt = typer.style(first, fg=val_color) if val_color else first
        typer.echo(f"{label_txt}{pad}{first_txt}")
        for line in rest:
            cont = " " * align + (
                typer.style(line, fg=val_color) if val_color else line
            )
            typer.echo(cont)
    else:
        # Already multiline → indent properly
        lines = text.splitlines() or [text]
        first = lines[0]
        first_txt = typer.style(first, fg=val_color) if val_color else first
        typer.echo(f"{label_txt}{pad}{first_txt}")
        for line in lines[1:]:
            cont = " " * align + (
                typer.style(line, fg=val_color) if val_color else line
            )
            typer.echo(cont)


def bullet(
    text: str,
    *,
    level: str | None = None,
    accent: bool = False,
    indent: int = 0,
) -> None:
    """Display a bulleted item.

    Args:
        text: The bullet content.
        level: Semantic level (`"info" | "ok" | "warn" | "error"`).
            Maps to a color.
        accent: If True, apply bold + color emphasis.
        indent: Number of spaces to indent the bullet.
    """
    prefix = "•"
    body = " " * max(0, indent) + f"{prefix} {text}"
    if accent or level:
        typer.echo(
            typer.style(body, fg=_color_for(level) or typer.colors.GREEN, bold=accent)
        )
    else:
        typer.echo(body)


def step(
    n: int,
    text: str,
    *,
    level: str | None = None,
    indent: int = 0,
) -> None:
    """Display a numbered step.

    Args:
        n: The step number.
        text: The step description.
        level: Semantic level (`"info" | "ok" | "warn" | "error"`).
            Maps to a color.
        indent: Number of spaces to indent the step.
    """
    prefix = typer.style(f"{n}.", bold=True)
    body = " " * max(0, indent) + f"{prefix} {text}"
    if level:
        typer.echo(typer.style(body, fg=_color_for(level)))
    else:
        typer.echo(body)


# ====== High-level helpers ========================================================


def info(text: str) -> None:
    """Shortcut for an informational bullet."""
    bullet(text, level="info", accent=True)


def success(text: str) -> None:
    """Shortcut for a success bullet."""
    bullet(text, level="ok", accent=True)


def warn(text: str) -> None:
    """Shortcut for a warning bullet."""
    bullet(text, level="warn", accent=True)


def error(text: str) -> None:
    """Shortcut for an error bullet."""
    bullet(text, level="error", accent=True)


def trace(text: str) -> None:
    """Verbose/diagnostic log, displayed in a dimmed style."""
    typer.echo(typer.style(text, dim=True))
