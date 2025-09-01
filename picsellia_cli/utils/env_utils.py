import os
from pathlib import Path
import typer
from dotenv import load_dotenv


def resolve_env_from_host(host: str) -> str:
    host = host.lower()
    if "staging" in host:
        return "STAGING"
    elif "localhost" in host or "127.0.0.1" in host:
        return "LOCAL"
    else:
        return "PROD"


def require_env_var(
    name: str,
    prompt_if_missing: bool = False,
    prompt_label: str | None = None,
    hide_input=False,
) -> str:
    value = os.getenv(name)
    if value:
        return value

    if not prompt_if_missing:
        raise typer.Exit(
            typer.style(
                f"❌ Missing required environment variable: {name}", fg=typer.colors.RED
            )
        )

    label = prompt_label or f"Enter value for {name}"
    value = typer.prompt(label, hide_input=hide_input)
    os.environ[name] = value
    _write_env_var(name, value)
    return value


def _write_env_var(key: str, value: str):
    env_file = Path.home() / ".config" / "picsellia" / ".env"
    env_file.parent.mkdir(parents=True, exist_ok=True)

    if env_file.exists():
        existing = env_file.read_text().splitlines()
    else:
        existing = []

    if not any(line.startswith(f"{key}=") for line in existing):
        with env_file.open("a") as f:
            f.write(f"{key}={value}\n")


def get_api_token_from_host(host: str) -> str:
    """
    Resolve the API token for a given host using the environment config.
    Will prompt and persist if missing.
    """
    suffix = resolve_env_from_host(host)
    token_var = f"PICSELLIA_API_TOKEN_{suffix}"
    return require_env_var(
        token_var,
        prompt_if_missing=True,
        prompt_label=f"🔐 Enter API token for host {host} ({suffix})",
        hide_input=True,
    )


def get_host_env_config(host: str) -> dict[str, str]:
    """
    Dynamically load env vars based on host.
    Prompt and persist if any are missing.
    """
    suffix = resolve_env_from_host(host)
    host_var = f"PICSELLIA_HOST_{suffix}"
    org_var = f"PICSELLIA_ORGANIZATION_NAME_{suffix}"

    return {
        "api_token": get_api_token_from_host(host=host),
        "organization_name": require_env_var(
            org_var,
            prompt_if_missing=True,
            prompt_label=f"🏢 Enter organization name for {suffix}",
        ),
        "host": require_env_var(
            host_var,
            prompt_if_missing=True,
            prompt_label=f"🌍 Enter host URL for {suffix}",
        ),
    }


def ensure_env_vars(host: str = "prod"):
    """
    Load .env to memory.
    """
    suffix = resolve_env_from_host(host=host)
    env_file = Path.home() / ".config" / "picsellia" / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)

    for var_base, label, hide in [
        ("PICSELLIA_API_TOKEN", f"🔐 Enter your Picsellia API token ({suffix})", True),
        ("PICSELLIA_HOST", f"🌍 Enter the Picsellia host ({suffix})", False),
        (
            "PICSELLIA_ORGANIZATION_NAME",
            f"🏢 Enter your Picsellia organization name ({suffix})",
            False,
        ),
    ]:
        full_var = f"{var_base}_{suffix}"
        require_env_var(
            full_var, prompt_if_missing=True, prompt_label=label, hide_input=hide
        )


def get_available_envs():
    """
    Scans environment variables for configured deployment targets.
    Returns a list of dicts with keys: host, api_token, organization_name
    """
    envs = []
    suffixes = ["PROD", "STAGING", "LOCAL"]

    for suffix in suffixes:
        token = os.getenv(f"PICSELLIA_API_TOKEN_{suffix}")
        org = os.getenv(f"PICSELLIA_ORGANIZATION_NAME_{suffix}")
        host = os.getenv(f"PICSELLIA_HOST_{suffix}")

        if token and org and host:
            envs.append(
                {
                    "api_token": token,
                    "organization_name": org,
                    "host": host,
                    "suffix": suffix,
                }
            )

    if not envs:
        raise typer.Exit("❌ No valid deployment environments found in .env")

    return envs
