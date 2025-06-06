import os
import typer


def require_env_var(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise typer.Exit(
            typer.style(
                f"❌ Missing required environment variable: {name}", fg=typer.colors.RED
            )
        )
    return value
