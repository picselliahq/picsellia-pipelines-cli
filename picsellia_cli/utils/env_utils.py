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


def ensure_env_vars():
    """
    Prompt for API_TOKEN, ORGANIZATION_NAME and HOST if not found in environment.
    Sets them in os.environ for immediate use.
    """
    if not os.getenv("API_TOKEN"):
        os.environ["API_TOKEN"] = typer.prompt(
            "🔐 Enter your API token", hide_input=True
        )

    if not os.getenv("ORGANIZATION_NAME"):
        os.environ["ORGANIZATION_NAME"] = typer.prompt(
            "🏢 Enter your organization name"
        )

    if not os.getenv("HOST"):
        os.environ["HOST"] = typer.prompt(
            "🌍 Enter the Picsellia host", default="https://app.picsellia.com"
        )
