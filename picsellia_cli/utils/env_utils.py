import os
from enum import Enum
from pathlib import Path

import typer
from dotenv import load_dotenv

ENV_FILE = Path.home() / ".config" / "picsellia" / ".env"
ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


class Environment(str, Enum):
    PROD = "PROD"
    STAGING = "STAGING"
    LOCAL = "LOCAL"

    @property
    def url(self) -> str:
        return {
            Environment.PROD: "https://app.picsellia.com",
            Environment.STAGING: "https://staging.picsellia.com",
            Environment.LOCAL: "http://localhost:8000",
        }[self]

    @classmethod
    def list(cls) -> list[str]:
        return [e.value for e in cls]


def _env_key(organization: str, env: str, key: str) -> str:
    return f"PICSELLIA_{organization}_{env}_{key}".upper()


def _write_env_var(key: str, value: str):
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    if not any(line.startswith(f"{key}=") for line in lines):
        with ENV_FILE.open("a") as f:
            f.write(f"{key}={value}\n")


def _require_env_var(key: str, prompt: str, hide_input=False) -> str:
    value = os.getenv(key)
    if value:
        return value
    value = typer.prompt(prompt, hide_input=hide_input)
    os.environ[key] = value
    _write_env_var(key, value)
    return value


def resolve_env(selected_env: str) -> Environment:
    """
    Convert a string environment into an Environment enum,
    with validation and error handling.

    Args:
        selected_env: Environment name as string (e.g. "prod", "staging", "local").

    Returns:
        Environment: Enum value (Environment.PROD, STAGING, LOCAL).

    Raises:
        typer.Exit: If the environment is invalid.
    """
    try:
        return Environment(selected_env.upper())
    except ValueError:
        typer.echo(
            f"❌ Invalid environment '{selected_env}'. Must be one of {[e.value for e in Environment]}"
        )
        raise typer.Exit(code=1)


def get_env_config(organization: str, env: Environment) -> dict[str, str]:
    env_name = env.value.upper()

    api_token_key = _env_key(organization, env_name, "API_TOKEN")

    api_token = _require_env_var(
        api_token_key, f"🔐 API token for {organization}@{env_name}", hide_input=True
    )

    return {
        "organization_name": organization,
        "api_token": api_token,
        "host": env.url,
        "env": env_name,
    }


def get_available_configs() -> list[dict[str, str]]:
    configs = []
    for line in ENV_FILE.read_text().splitlines():
        if "API_TOKEN" in line:
            parts = line.split("=")[0].split("_")
            _, org, env_str, _ = parts
            try:
                env = Environment(env_str.upper())
                config = get_env_config(org, env)
                configs.append(config)
            except Exception:
                continue
    if not configs:
        typer.echo("❌ No valid Picsellia configurations found.")
        raise typer.Exit()
    return configs
