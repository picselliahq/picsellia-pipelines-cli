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
    return f"PICSELLIA_{organization}_{env.upper()}_{key.upper()}"


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
            key = line.split("=")[0]
            parts = key.split("_")

            if len(parts) < 4 or parts[0] != "PICSELLIA":
                continue

            org = "_".join(parts[1:-2])  # tout ce qui est entre PICSELLIA et ENV
            env_str = parts[-2]

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


def parse_env_key(key: str) -> tuple[str, str] | None:
    """
    Parse a PICSELLIA env key of the form:
    PICSELLIA_{organization}_{ENV}_API_TOKEN

    Returns:
        (organization, env_str) if valid, else None
    """
    parts = key.split("_")
    if len(parts) < 4 or parts[0] != "PICSELLIA" or parts[-2:] != ["API", "TOKEN"]:
        return None

    # Chercher l'env dans les parties
    for i, part in enumerate(parts):
        if part.upper() in [e.value for e in Environment]:
            org = "_".join(parts[1:i])  # tout ce qui est entre PICSELLIA et ENV
            return org, part.upper()

    return None


def get_organization_for_env(env: Environment) -> str:
    env_name = env.value.upper()
    orgs_for_env = []

    if not ENV_FILE.exists():
        typer.echo("❌ No .env file found with Picsellia credentials.")
        raise typer.Exit(code=1)

    for line in ENV_FILE.read_text().splitlines():
        if line.strip() and "API_TOKEN" in line:
            key = line.split("=")[0]
            parsed = parse_env_key(key)
            if not parsed:
                continue
            org, env_str = parsed

            if env_str == env_name:
                orgs_for_env.append(org)

    if not orgs_for_env:
        typer.echo(f"❌ No organization found for environment {env_name}.")
        raise typer.Exit(code=1)

    if len(orgs_for_env) > 1:
        typer.echo(
            f"❌ Multiple organizations found for environment {env_name}: {', '.join(orgs_for_env)}. "
            f"Please specify one with --organization."
        )
        raise typer.Exit(code=1)

    return orgs_for_env[0]
