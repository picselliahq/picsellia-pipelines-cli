import os
import typer
from pathlib import Path
from dotenv import load_dotenv


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
    Prompt for PICSELLIA_API_TOKEN, PICSELLIA_ORGANIZATION_NAME and PICSELLIA_HOST if not found in environment.
    Sets them in os.environ for immediate use and saves them to a .env file.
    """
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)

    env_vars = {
        "PICSELLIA_API_TOKEN": {
            "prompt": "🔐 Enter your Picsellia API token",
            "hide_input": True,
        },
        "PICSELLIA_ORGANIZATION_NAME": {
            "prompt": "🏢 Enter your Picsellia organization name",
            "hide_input": False,
        },
        "PICSELLIA_HOST": {
            "prompt": "🌍 Enter the Picsellia host",
            "default": "https://app.picsellia.com",
            "hide_input": False,
        },
    }

    existing_lines = []
    if env_file.exists():
        existing_lines = env_file.read_text().splitlines()

    new_vars = []

    for var, settings in env_vars.items():
        if not os.getenv(var):
            if settings.get("hide_input"):
                value = typer.prompt(settings["prompt"], hide_input=True)
            else:
                value = typer.prompt(
                    settings["prompt"], default=settings.get("default", None)
                )
            os.environ[var] = value

            if not any(line.startswith(f"{var}=") for line in existing_lines):
                new_vars.append(f"{var}={value}")

    if new_vars:
        with env_file.open("a") as f:
            for line in new_vars:
                f.write(f"{line}\n")
