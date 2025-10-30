import json
import os
from enum import Enum
from pathlib import Path

import typer
from dotenv import load_dotenv

APP_DIR = Path.home() / ".config" / "picsellia"
ENV_FILE = APP_DIR / ".env"
CTX_FILE = APP_DIR / "context.json"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)


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


def resolve_env(selected_env: str | Environment | None) -> Environment:
    if isinstance(selected_env, Environment):
        return selected_env
    try:
        return Environment((selected_env or "PROD").upper())
    except ValueError as err:
        typer.echo(
            f"❌ Invalid environment '{selected_env}'. Must be one of {Environment.list()}"
        )
        raise typer.Exit(1) from err


def _env_key(org: str, env: Environment) -> str:
    return f"PICSELLIA_{org}_{env.value}_API_TOKEN"


def _read_current_context() -> tuple[str | None, Environment | None]:
    if not CTX_FILE.exists():
        return None, None
    try:
        ctx = json.loads(CTX_FILE.read_text())
        org = ctx.get("organization")
        env_str = ctx.get("env")
        env = Environment(env_str) if env_str else None
        return org, env
    except Exception:
        return None, None


def get_env_config(
    organization: str | None = None, env: str | Environment | None = None
) -> dict[str, str]:
    """
    Return the active environment configuration:
      - if organization/env are provided → use them
      - otherwise → read the current context (from `auth login`)
    Never prompts. If the token is missing, show an error suggesting `pxl auth login`.
    """
    org_ctx, env_ctx = _read_current_context()

    org = organization or org_ctx
    ev = resolve_env(env or env_ctx)

    if not org or not ev:
        typer.echo(
            "❌ No current context. Run: pxl auth login --organization <ORG> --env <ENV>"
        )
        raise typer.Exit(1)

    # (Re)load .env to ensure variables are available
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=False)

    key = _env_key(org, ev)
    token = os.getenv(key)
    if not token:
        typer.echo(
            f"❌ No API token found for {org}@{ev.value}.\n"
            f"   Run: pxl auth login --organization {org} --env {ev.value}"
        )
        raise typer.Exit(1)

    return {
        "organization_name": org,
        "api_token": token,
        "host": ev.url,
        "env": ev.value,
    }
