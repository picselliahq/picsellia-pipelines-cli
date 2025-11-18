import json
import os
from enum import Enum
from pathlib import Path

import typer
from dotenv import load_dotenv

APP_DIR = Path.home() / ".config" / "picsellia"
ENV_FILE = APP_DIR / ".env"
CTX_FILE = APP_DIR / "context.json"

CUSTOM_ENV_KEY = "PICSELLIA_CUSTOM_ENV"

APP_DIR.mkdir(parents=True, exist_ok=True)
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)


class Environment(str, Enum):
    PROD = "PROD"
    STAGING = "STAGING"
    LOCAL = "LOCAL"
    CUSTOM = "CUSTOM"

    @property
    def url(self) -> str:
        if self is Environment.CUSTOM:
            ensure_env_loaded()
            custom_url = os.getenv(CUSTOM_ENV_KEY)
            if not custom_url:
                typer.echo(
                    "❌ Custom environment URL is not configured.\n"
                    "   Set it by running: pxl auth login --env CUSTOM"
                )
                raise typer.Exit(1)
            return custom_url

        return {
            Environment.PROD: "https://app.picsellia.com",
            Environment.STAGING: "https://staging.picsellia.com",
            Environment.LOCAL: "http://localhost:8000",
        }[self]

    @classmethod
    def list(cls) -> list[str]:
        return [e.value for e in cls]


def resolve_env(selected_env: str | Environment | None) -> Environment | None:
    """
    Normalize an env value to an Environment enum.

    - If selected_env is None -> return None (no env resolved).
    - If it's already an Environment -> return it as-is.
    - If it's a string -> try to cast to Environment, otherwise exit with an error.
    """
    if selected_env is None:
        return None

    if isinstance(selected_env, Environment):
        return selected_env

    try:
        return Environment(selected_env.upper())
    except ValueError as err:
        typer.echo(
            f"❌ Invalid environment '{selected_env}'. Must be one of {Environment.list()}"
        )
        raise typer.Exit(1) from err


# ---------------------
# Low-level key & files
# ---------------------


def env_key(org: str, env: Environment) -> str:
    return f"PICSELLIA_{org}_{env.value}_API_TOKEN"


def ensure_env_loaded() -> None:
    """(Re)load ~/.config/picsellia/.env into process env."""
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=False)


def write_env_line(key: str, value: str) -> None:
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + ("\n" if lines else ""))

    os.environ[key] = value


def get_custom_env_url() -> str | None:
    """Return the custom environment base URL if configured."""
    ensure_env_loaded()
    return os.getenv(CUSTOM_ENV_KEY)


def set_custom_env_url(url: str) -> None:
    """Persist the custom environment base URL to ~/.config/picsellia/.env."""
    if not url:
        typer.echo("❌ Custom environment URL cannot be empty.")
        raise typer.Exit(1)
    write_env_line(CUSTOM_ENV_KEY, url)
    typer.secho(
        f"✓ Custom environment URL saved to {ENV_FILE}",
        fg=typer.colors.GREEN,
    )


# ---------------------
# Context helpers
# ---------------------


def set_current_context(org: str, env: Environment) -> None:
    CTX_FILE.write_text(json.dumps({"organization": org, "env": env.value}))


def clear_current_context() -> None:
    if CTX_FILE.exists():
        CTX_FILE.unlink()


def read_current_context() -> tuple[str | None, Environment | None]:
    if not CTX_FILE.exists():
        return None, None
    try:
        ctx = json.loads(CTX_FILE.read_text())
        org = ctx.get("organization")
        env_str = ctx.get("env")
        ev = Environment(env_str) if env_str else None
        return org, ev
    except Exception:
        return None, None


# ---------------------
# Token helpers
# ---------------------


def token_for(org: str, env: Environment) -> str | None:
    """Return token for org@env from .env (or None)."""
    ensure_env_loaded()
    return os.getenv(env_key(org, env))


def ensure_token(
    org: str,
    env: Environment,
    *,
    prompt_label: str | None = None,
    token_override: str | None = None,
) -> None:
    """
    Ensure a token exists for org@env. If missing, prompt & persist it.
    """
    if token_override:
        write_env_line(env_key(org, env), token_override)
        typer.secho("✓ Token saved.", fg=typer.colors.GREEN)
        return

    if token_for(org, env):
        return

    label = prompt_label or f"Enter Picsellia API token for {org}@{env.value}"
    token = typer.prompt(label, hide_input=True)
    write_env_line(env_key(org, env), token)
    typer.secho("✓ Token saved.", fg=typer.colors.GREEN)


# ---------------------
# High-level config (used by commands)
# ---------------------


def get_env_config(
    organization: str | None = None,
    env: str | Environment | None = None,
) -> dict[str, str]:
    """
    Return the active environment configuration:

      - if organization/env are provided → they override the current context
      - otherwise → read the current context (from `auth login`)

    Never prompts. If the token is missing, show an error suggesting `pxl-pipeline login`.
    """
    org_ctx, env_ctx = read_current_context()

    org = organization or org_ctx
    resolved_env = resolve_env(env if env is not None else env_ctx)

    if not org or not resolved_env:
        typer.echo("❌ No current context. Run: pxl-pipeline login")
        raise typer.Exit(1)

    ensure_env_loaded()
    token = token_for(org, resolved_env)
    if not token:
        typer.echo(
            f"❌ No API token found for {org}@{resolved_env.value}.\n"
            "   Run: pxl-pipeline login"
        )
        raise typer.Exit(1)

    return {
        "organization_name": org,
        "api_token": token,
        "host": resolved_env.url,
        "env": resolved_env.value,
    }
