from __future__ import annotations

import json
import textwrap
from contextlib import contextmanager
from typing import Any, Optional

import typer

# ====== Configuration par défaut ==================================================

_DEFAULT_WIDTH = 72
_LABEL_ALIGN = 22  # largeur réservée au label dans kv()


# ====== Outils de style ===========================================================


def _color_for(level: str | None):
    mapping = {
        "info": typer.colors.BLUE,
        "ok": typer.colors.GREEN,
        "warn": typer.colors.YELLOW,
        "error": typer.colors.RED,
        "muted": typer.colors.WHITE,
    }
    return mapping.get(level or "", None)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, indent=2, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


# ====== Primitives d'affichage ====================================================


def hr(*, width: int = _DEFAULT_WIDTH, char: str = "─", dim: bool = True) -> None:
    line = char * max(8, width)
    typer.echo(typer.style(line, dim=dim))


def section(title: str, *, width: int = _DEFAULT_WIDTH) -> None:
    hr(width=width)
    typer.echo(typer.style(f" {title}", bold=True))
    hr(width=width)


@contextmanager
def section_cm(title: str, *, width: int = _DEFAULT_WIDTH):
    section(title, width=width)
    try:
        yield
    finally:
        hr(width=width)


def kv(
    label: str,
    value: Any,
    *,
    color: Optional[str] = None,
    level: str | None = None,
    align: int = _LABEL_ALIGN,
    width: int = _DEFAULT_WIDTH,
    wrap: bool = True,
) -> None:
    """
    Affiche une paire clé/valeur avec alignement propre.
    - color: couleur explicite (typer.colors.*) prioritaire sur level
    - level: 'info'|'ok'|'warn'|'error' (palette cohérente)
    - wrap: retour à la ligne pour longues valeurs
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
        # wrap “douce” en gardant l'alignement des lignes suivantes
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
        # multi-lignes déjà présentes → indenter proprement
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
    """
    Puce simple. level→ palette ('info'|'ok'|'warn'|'error').
    accent=True → texte en gras + couleur.
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
    """
    Étape numérotée. level→ palette ('info'|'ok'|'warn'|'error').
    """
    prefix = typer.style(f"{n}.", bold=True)
    body = " " * max(0, indent) + f"{prefix} {text}"
    if level:
        typer.echo(typer.style(body, fg=_color_for(level)))
    else:
        typer.echo(body)


# ====== Helpers de haut niveau ====================================================


def info(text: str) -> None:
    bullet(text, level="info", accent=True)


def success(text: str) -> None:
    bullet(text, level="ok", accent=True)


def warn(text: str) -> None:
    bullet(text, level="warn", accent=True)


def error(text: str) -> None:
    bullet(text, level="error", accent=True)


def trace(text: str) -> None:
    """Log verbeux/diagnostic en atténué."""
    typer.echo(typer.style(text, dim=True))
