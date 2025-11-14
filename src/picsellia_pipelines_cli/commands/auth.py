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
            "        pxl-pipeline login"
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
    token_override: str | None = None,
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
        ensure_token(
            organization,
            env,
            prompt_label=token_prompt_label,
            token_override=token_override,
        )

    set_current_context(organization, env)

    _test_connection(organization, env)

    typer.secho(
        f"✓ Context {success_verb} to org={organization} env={env.value}",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"Credentials file: {ENV_FILE}")


def _list_saved_contexts() -> list[tuple[str, Environment]]:
    """Return all org/env pairs that have a stored API token."""
    ensure_env_loaded()

    if not ENV_FILE.exists():
        return []

    contexts: set[tuple[str, Environment]] = set()
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _ = line.split("=", 1)
        # We store tokens as PICSELLIA_{ORG}_{ENV}_API_TOKEN
        if not key.startswith("PICSELLIA_") or not key.endswith("_API_TOKEN"):
            continue

        middle = key[len("PICSELLIA_") : -len("_API_TOKEN")]
        parts = middle.split("_")
        if len(parts) < 2:
            continue

        env_str = parts[-1]
        org = "_".join(parts[:-1])

        try:
            env = Environment(env_str)
        except ValueError:
            continue

        contexts.add((org, env))

    return sorted(contexts, key=lambda x: (x[0].lower(), x[1].value))


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
    token: Annotated[
        str | None,
        typer.Option("--token", help="Picsellia API token (or set PXL_API_TOKEN)."),
    ] = None,
):
    """Log in to Picsellia and set the active organization/environment context."""

    current_org, current_env = read_current_context()

    # Case 1 — user already logged in and no params provided
    if current_org and current_env and organization is None and env is None:
        typer.echo(f"Already logged in as {current_org}@{current_env.value}.")
        if not typer.confirm("Do you want to log in as another user?", default=False):
            typer.echo("Keeping current login.")
            raise typer.Exit()

    # Case 2 — if parameters provided, override directly (acts like switch)
    organization, env = _prompt_org_and_env(organization, env)

    _configure_and_persist_context(
        organization,
        env,
        token_prompt_label=None,  # default label from ensure_token
        success_verb="set",
        token_override=token,
    )


@app.command("logout")
def logout():
    """Clear the current context without removing stored API tokens."""
    clear_current_context()
    typer.secho(
        "✓ Logged out: current context cleared (tokens preserved).",
        fg=typer.colors.GREEN,
    )


@app.command("whoami")
def whoami():
    """Show the currently active organization and environment."""
    org, env = read_current_context()
    if not org or not env:
        typer.echo("No current context. Run: pxl-pipeline login")
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
    """Switch to a different organization/environment context."""
    current_org, current_env = read_current_context()

    # If user provided flags, behave like a direct switch
    if organization is not None or env is not None:
        organization, env = _prompt_org_and_env(organization, env)
        _configure_and_persist_context(
            organization,
            env,
            token_prompt_label=f"Enter Picsellia API token for {organization}@{env.value}",
            success_verb="switched",
        )
        return

    # No flags → interactive selection among saved contexts
    saved_contexts = _list_saved_contexts()

    if not saved_contexts:
        typer.echo(
            "No saved contexts found. Please enter a new organization/environment."
        )
        organization, env = _prompt_org_and_env(None, None)
        _configure_and_persist_context(
            organization,
            env,
            token_prompt_label=f"Enter Picsellia API token for {organization}@{env.value}",
            success_verb="switched",
        )
        return

    typer.echo("Available contexts:")
    for idx, (org, ev) in enumerate(saved_contexts, start=1):
        marker = ""
        if current_org == org and current_env == ev:
            marker = " (current)"
        typer.echo(f"  {idx}. {org}@{ev.value}{marker}")
    typer.echo("  n. Use a new organization/environment")

    choice = typer.prompt("Select a context (number or 'n')", default="1").strip()

    if choice.lower().startswith("n"):
        organization, env = _prompt_org_and_env(None, None)
    else:
        try:
            index = int(choice)
            if index < 1 or index > len(saved_contexts):
                raise ValueError
            organization, env = saved_contexts[index - 1]
        except Exception as e:
            typer.echo("❌ Invalid selection.")
            raise typer.Exit(1) from e

    _configure_and_persist_context(
        organization,
        env,
        token_prompt_label=f"Enter Picsellia API token for {organization}@{env.value}",
        success_verb="switched",
    )
