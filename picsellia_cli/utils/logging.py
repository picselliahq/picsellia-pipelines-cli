from typing import Optional
import typer


def hr() -> None:
    typer.echo(typer.style("─" * 72, dim=True))


def section(title: str) -> None:
    hr()
    typer.echo(typer.style(f" {title}", bold=True))
    hr()


def kv(label: str, value: object, *, color: Optional[str] = None) -> None:
    """Key/Value line with optional color for the value."""
    if value is None:
        return
    val = str(value).strip()
    if not val or val.lower() == "unknown":
        return
    label_txt = typer.style(f"{label}:", bold=True)
    val_txt = typer.style(val, fg=color) if color else val
    typer.echo(f"{label_txt} {val_txt}")


def bullet(text: str, *, accent: bool = False) -> None:
    prefix = "•"
    line = f"{prefix} {text}"
    typer.echo(typer.style(line, fg=typer.colors.GREEN, bold=True) if accent else line)


def step(n: int, text: str, *, accent: bool = False) -> None:
    prefix = typer.style(f"{n}.", bold=True)
    line = f"{prefix} {text}"
    typer.echo(typer.style(line, fg=typer.colors.GREEN, bold=True) if accent else line)
