from __future__ import annotations

from typing import Annotated

import typer

from picsellia_pipelines_cli.utils.env_utils import (
    ENV_FILE,
    Environment,
    clear_current_context,
    ensure_env_loaded,
    ensure_token,
    read_current_context,
    set_current_context,
    token_for,
)

app = typer.Typer(help="Authenticate and manage Picsellia CLI context.")

ENV_CHOICES_STR = ", ".join(Environment.list())


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
    cur_org, cur_env = read_current_context()

    if not organization:
        organization = typer.prompt("Organization", default=cur_org or "")
    if not env:
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

    ensure_env_loaded()
    if token_for(organization, env) is None:
        ensure_token(organization, env)

    set_current_context(organization, env)
    typer.secho(
        f"✓ Context set to org={organization} env={env.value}", fg=typer.colors.GREEN
    )
    typer.echo(f"Credentials file: {ENV_FILE}")


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
    cur_org, cur_env = read_current_context()

    if not organization:
        organization = typer.prompt("Organization", default=cur_org or "")
    if not env:
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

    ensure_env_loaded()
    if token_for(organization, env) is None:
        ensure_token(
            organization,
            env,
            prompt_label=f"Enter Picsellia API token for {organization}@{env.value}",
        )

    set_current_context(organization, env)
    typer.secho(
        f"✓ Context switched to org={organization} env={env.value}",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"Credentials file: {ENV_FILE}")
