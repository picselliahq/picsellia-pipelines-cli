from __future__ import annotations

from typing import Annotated

import typer

from picsellia_pipelines_cli.utils.env_utils import (
    CTX_FILE,
    ENV_FILE,
    Environment,
    clear_current_context,
    ensure_env_loaded,
    ensure_token,
    get_custom_env_url,
    get_env_config,
    read_current_context,
    set_current_context,
    set_custom_env_url,
    token_for,
)
from picsellia_pipelines_cli.utils.initializer import init_client

app = typer.Typer(help="Authenticate and manage Picsellia CLI context.")

ENV_CHOICES_STR = ", ".join(Environment.list())
CUSTOM_ENV_KEY = "PICSELLIA_CUSTOM_ENV"


def _maybe_configure_custom_env() -> None:
    """Prompt for a custom base URL if needed and persist it."""
    existing = get_custom_env_url()
    default = existing or ""
    custom_url = typer.prompt(
        "Custom Picsellia base URL (e.g. https://my.picsellia.internal)",
        default=default,
    ).strip()

    if not custom_url:
        typer.echo("❌ A custom URL is required when using env=CUSTOM.")
        raise typer.Exit(1)

    set_custom_env_url(custom_url)


def _prompt_org_and_env(
    organization: str | None,
    env: Environment | None,
) -> tuple[str, Environment]:
    """Shared logic to resolve organization and environment (with prompts)."""
    cur_org, cur_env = read_current_context()

    if not organization:
        organization = typer.prompt("Organization", default=cur_org or "")

    if env is None:
        env_str = typer.prompt(
            f"Environment ({ENV_CHOICES_STR})",
            default=(cur_env.value if cur_env else "PROD"),
        )
        try:
            env = Environment(env_str.upper())
        except Exception as err:
            typer.echo(
                f"❌ Invalid environment '{env_str}'. Must be one of {Environment.list()}"
            )
            raise typer.Exit(1) from err

    if not organization:
        typer.echo("❌ Organization is required.")
        raise typer.Exit(1)

    return organization, env


def _test_connection(organization: str, env: Environment) -> None:
    """
    Try to build a Picsellia client with the current configuration.
    If it fails, explain how to fix .env / context.json and exit.
    """
    try:
        env_config = get_env_config(organization=organization, env=env)
        init_client(env_config)
    except Exception as err:
        typer.secho(
            "❌ Failed to connect to Picsellia with the current context.",
            fg=typer.colors.RED,
        )
        typer.echo("")
        typer.echo(f"Error from client: {err}")
        typer.echo("")
        typer.echo("You can fix your configuration in ~/.config/picsellia:")
        typer.echo(f"  • Context file: {CTX_FILE}")
        typer.echo(
            "    - To fix the organization name, update the 'organization' field\n"
            "      or re-run:\n"
            "        pxl-pipeline login --organization <ORG> --env <ENV>"
        )
        typer.echo("")
        typer.echo(f"  • Credentials file: {ENV_FILE}")
        typer.echo(
            f"    - To fix the API token, edit the line:\n"
            f"        PICSELLIA_{organization}_{env.value}_API_TOKEN=...\n"
            "      and replace the value after '=' with a valid token."
        )
        typer.echo("")
        typer.echo(
            f"    - For a CUSTOM environment URL, edit the line:\n"
            f"        {CUSTOM_ENV_KEY}=...\n"
            "      and set it to your Picsellia base URL "
            "(e.g. https://my.picsellia.internal)."
        )
        raise typer.Exit(1) from err


def _configure_and_persist_context(
    organization: str,
    env: Environment,
    *,
    token_prompt_label: str | None,
    success_verb: str,
) -> None:
    """
    Shared logic for:
    - CUSTOM env URL configuration
    - ensuring token exists
    - persisting current context
    - printing success message
    """
    if env is Environment.CUSTOM:
        _maybe_configure_custom_env()

    ensure_env_loaded()
    if token_for(organization, env) is None:
        ensure_token(organization, env, prompt_label=token_prompt_label)

    set_current_context(organization, env)

    _test_connection(organization, env)

    typer.secho(
        f"✓ Context {success_verb} to org={organization} env={env.value}",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"Credentials file: {ENV_FILE}")


@app.command("login")
def login(
    organization: Annotated[
        str | None,
        typer.Option("--organization", "-o", help="Organization slug/name"),
    ] = None,
    env: Annotated[
        Environment | None,
        typer.Option("--env", "-e", help=f"One of: {ENV_CHOICES_STR}"),
    ] = None,
):
    """
    - If a token already exists for ORG+ENV, reuse it (no prompt).
    - Otherwise, prompt for the token and save it.
    - ORG/ENV can be provided as options; if omitted, they will be prompted.
    - Always sets the current context (ORG+ENV).
    """
    organization, env = _prompt_org_and_env(organization, env)
    _configure_and_persist_context(
        organization,
        env,
        token_prompt_label=None,  # default label from ensure_token
        success_verb="set",
    )


@app.command("logout")
def logout():
    """Unset the current context only. Tokens stored on disk are preserved."""
    clear_current_context()
    typer.secho(
        "✓ Logged out: current context cleared (tokens preserved).",
        fg=typer.colors.GREEN,
    )


@app.command("whoami")
def whoami():
    org, env = read_current_context()
    if not org or not env:
        typer.echo("No current context. Run: pxl auth login")
        raise typer.Exit(1)

    has_token = token_for(org, env) is not None
    typer.echo(f"Context: org={org} env={env.value}")
    typer.echo(f"Token stored: {'yes' if has_token else 'no'}")


@app.command("switch")
def switch(
    organization: Annotated[
        str | None,
        typer.Option("--organization", "-o", help="Organization slug/name"),
    ] = None,
    env: Annotated[
        Environment | None,
        typer.Option("--env", "-e", help=f"One of: {ENV_CHOICES_STR}"),
    ] = None,
):
    """Change the current context; if the target org/env has no token saved, prompt for it and save."""
    organization, env = _prompt_org_and_env(organization, env)
    _configure_and_persist_context(
        organization,
        env,
        token_prompt_label=f"Enter Picsellia API token for {organization}@{env.value}",
        success_verb="switched",
    )
