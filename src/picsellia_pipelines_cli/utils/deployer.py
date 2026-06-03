import json
import os
import subprocess
import sys
from enum import Enum
from pathlib import Path

import typer
from semver import VersionInfo

from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig


class Bump(str, Enum):
    patch = "patch"
    minor = "minor"
    major = "major"
    rc = "rc"
    final = "final"


def _detect_registry_host(image_name: str) -> str | None:
    first = (image_name or "").split("/", 1)[0]
    if not first:
        return None
    if "." in first or ":" in first or first == "localhost":
        return first
    return None


def _validate_registry_path(image_name: str, default_ns: str | None = None) -> str:
    """
    If an explicit registry is present, enforce 'host/<namespace>/<repo>' shape.
    Returns the (possibly suggested) image_name, or raises Exit with a friendly error.
    """
    registry = _detect_registry_host(image_name)
    if not registry:
        return image_name

    _, _, remainder = image_name.partition("/")
    if not remainder:
        typer.echo(
            f"❌ Invalid image name '{image_name}': missing repository path after registry host."
        )
        raise typer.Exit(1)

    parts = remainder.split("/")
    if len(parts) >= 2:
        return image_name

    repo = parts[0]
    suggestion_ns = (default_ns or "project").lower()
    suggestion = f"{registry}/{suggestion_ns}/{repo}"
    typer.echo(
        "❌ Invalid repository path for this registry. Harbor/OVH requires 'host/<project>/<repo>'.\n"
        f"   Current: {image_name}\n"
        f"   Try:     {suggestion}\n"
        "   Make sure the project/namespace exists in the registry and you have push rights.\n"
        "   Then update `docker.image_name` accordingly in your `config.toml`."
    )
    raise typer.Exit(1)


def _registry_config_keys(registry: str) -> list[str]:
    return [registry, f"https://{registry}", f"http://{registry}"]


def _docker_hub_config_keys() -> list[str]:
    return [
        "https://index.docker.io/v1/",
        "index.docker.io",
        "registry-1.docker.io",
        "https://registry-1.docker.io",
        "docker.io",
    ]


def _docker_config_path() -> Path:
    return Path.home() / ".docker" / "config.json"


def _load_docker_config() -> dict:
    config_path = _docker_config_path()
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _auth_entry_has_credentials(entry: object) -> bool:
    """True when an auths entry contains credentials or delegates to a cred helper."""
    if not isinstance(entry, dict):
        return False
    if entry.get("auth"):
        return True
    if entry.get("identitytoken"):
        return True
    if entry.get("username") and entry.get("password"):
        return True
    # Empty dict: Docker Desktop / credsStore stores secrets in the keychain.
    return entry == {}


def _registry_keys_in_config(config: dict, keys: list[str]) -> bool:
    auths = config.get("auths") or {}
    for key in keys:
        if key in auths and _auth_entry_has_credentials(auths[key]):
            return True

    cred_helpers = config.get("credHelpers") or {}
    for key in keys:
        if key in cred_helpers:
            return True

    return False


def registry_has_stored_credentials(registry: str) -> bool:
    """
    Return True when ~/.docker/config.json indicates credentials for this registry.

    Covers direct auth entries, empty auths placeholders used with credsStore,
    and per-registry credential helpers.
    """
    config = _load_docker_config()
    return _registry_keys_in_config(config, _registry_config_keys(registry))


def docker_hub_has_stored_credentials() -> bool:
    """Return True when Docker Hub credentials are present in the local Docker config."""
    config = _load_docker_config()
    if config.get("credsStore"):
        return True
    return _registry_keys_in_config(config, _docker_hub_config_keys())


def _docker_credentials_from_env() -> tuple[str, str] | None:
    username = os.getenv("DOCKERHUB_USERNAME") or os.getenv("DOCKER_USERNAME")
    password = (
        os.getenv("DOCKERHUB_TOKEN")
        or os.getenv("DOCKER_PASSWORD")
        or os.getenv("DOCKER_TOKEN")
    )
    if username and password:
        return username, password
    return None


def _run_docker_login(
    *,
    registry: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Run docker login and persist credentials in ~/.docker/config.json (Docker CLI default)."""
    command = ["docker", "login"]
    if username:
        command.extend(["-u", username])
    if password is not None:
        command.append("--password-stdin")
    if registry:
        command.append(registry)

    kwargs: dict = {"check": True, "text": True}
    if password is not None:
        kwargs["input"] = password
    else:
        kwargs["stdin"] = sys.stdin

    subprocess.run(command, **kwargs)


def _confirm_credentials_persisted(*, registry: str | None) -> None:
    if registry:
        ok = registry_has_stored_credentials(registry)
        target = registry
    else:
        ok = docker_hub_has_stored_credentials()
        target = "Docker Hub"

    if ok:
        typer.echo(
            f"✓ Credentials for {target} saved in {_docker_config_path()} "
            "(same as a normal `docker login`)."
        )
    else:
        typer.echo(
            typer.style(
                f"⚠️  Login succeeded but no credentials were found in {_docker_config_path()}. "
                "Future deploys may ask again.",
                fg=typer.colors.YELLOW,
            )
        )


def ensure_docker_login(image_name: str):
    """
    Ensure Docker auth is set for the target image's registry.

    Reuses credentials already stored by the Docker CLI in ~/.docker/config.json.
    When login is required, runs `docker login` the same way as manually — credentials
    are written to config.json (or your configured credsStore / keychain).

    Environment variables (non-interactive, CI-friendly):
        DOCKERHUB_USERNAME / DOCKER_USERNAME
        DOCKERHUB_TOKEN / DOCKER_PASSWORD / DOCKER_TOKEN
    """
    registry = _detect_registry_host(image_name)
    env_credentials = _docker_credentials_from_env()

    if registry:
        typer.echo(f"Detected registry: {registry}")
        if registry_has_stored_credentials(registry):
            typer.echo(f"Using cached Docker credentials for '{registry}'")
            return

        if env_credentials:
            user, token = env_credentials
            typer.echo(f"Logging in to '{registry}' with DOCKER_* env credentials…")
            _run_docker_login(registry=registry, username=user, password=token)
            _confirm_credentials_persisted(registry=registry)
            return

        typer.echo(f"Logging in to registry '{registry}' (credentials will be cached)…")
        try:
            _run_docker_login(registry=registry)
        except subprocess.CalledProcessError as err:
            typer.echo("❌ Docker registry login failed.")
            raise typer.Exit(1) from err

        _confirm_credentials_persisted(registry=registry)
        return

    # ── Docker Hub (image like 'namespace/repo', no registry host) ───────────
    namespace = image_name.split("/", 1)[0]
    if docker_hub_has_stored_credentials():
        typer.echo(
            "Using cached Docker Hub credentials "
            f"(push access to '{namespace}' must be granted to your account)."
        )
        return

    if env_credentials:
        user, token = env_credentials
        typer.echo("Logging in to Docker Hub with DOCKER_* env credentials…")
        try:
            _run_docker_login(username=user, password=token)
        except subprocess.CalledProcessError as err:
            typer.echo("❌ Docker Hub login failed.")
            raise typer.Exit(1) from err
        _confirm_credentials_persisted(registry=None)
        return

    typer.echo(
        f"Logging in to Docker Hub (credentials will be cached in {_docker_config_path()}).\n"
        f"Use an account with push access to the '{namespace}' namespace."
    )
    try:
        _run_docker_login()
    except subprocess.CalledProcessError as err:
        typer.echo("❌ Docker Hub login failed. Please check your credentials.")
        raise typer.Exit(1) from err

    _confirm_credentials_persisted(registry=None)


def build_docker_image_only(pipeline_dir: Path, full_image_name: str) -> str:
    """Build a Docker image from a pipeline directory.

    Args:
        pipeline_dir: Directory containing the Dockerfile.
        full_image_name: Full image name (including tag).

    Returns:
        The built image name.

    Raises:
        typer.Exit: If the pipeline directory or Dockerfile is missing,
            or if the build fails.
    """
    pipeline_path = pipeline_dir.resolve()
    dockerfile_path = pipeline_path / "Dockerfile"
    dockerignore_path = pipeline_path / ".dockerignore"

    if not pipeline_path.exists():
        typer.echo(f"Pipeline directory '{pipeline_dir}' not found.")
        raise typer.Exit()

    if not dockerfile_path.exists():
        typer.echo(f"Missing Dockerfile in '{pipeline_dir}'.")
        raise typer.Exit()

    if not dockerignore_path.exists():
        dockerignore_path.write_text(
            ".venv/\nvenv/\n__pycache__/\n*.pyc\n*.pyo\n.DS_Store\n"
        )

    build_command = ["docker", "build"]
    if sys.platform == "darwin":
        # Ensure Linux-targeted images can be built from macOS hosts (e.g. Apple Silicon).
        build_command.extend(["--platform", "linux/amd64"])

    build_command.extend(["-t", full_image_name, "-f", dockerfile_path, "."])

    typer.echo(f"Building Docker image '{full_image_name}'...")
    try:
        subprocess.run(
            build_command,
            cwd=str(pipeline_path),
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        typer.echo(
            typer.style(
                f"\n❌ Failed to build Docker image. Exit code {e.returncode}.",
                fg=typer.colors.RED,
                bold=True,
            )
        )
        raise typer.Exit(code=e.returncode) from e

    return full_image_name


def tag_docker_image(source_image: str, target_image: str) -> None:
    """Apply an additional tag to an existing local Docker image."""
    subprocess.run(
        ["docker", "tag", source_image, target_image],
        check=True,
        text=True,
    )


def push_docker_image_only(full_image_name: str):
    """Push a Docker image to its remote registry.

    Args:
        full_image_name: Full image name (including tag).
    """
    subprocess.run(
        ["docker", "push", full_image_name],
        check=True,
        text=True,
    )


def build_and_push_docker_image(
    pipeline_dir: Path, image_name: str, image_tags: list[str], force_login: bool = True
):
    """Build and push a Docker image for one or more tags.

    Builds the image once, applies additional tags locally, then pushes each tag.

    Args:
        pipeline_dir: Directory containing the Dockerfile.
        image_name: Base image name (without tag).
        image_tags: List of tags to build and push.
        force_login: If True, ensure Docker authentication before building.
    """
    if not image_tags:
        typer.echo("❌ No image tags provided for build/push.")
        raise typer.Exit(1)

    image_name = _validate_registry_path(image_name)

    if force_login:
        ensure_docker_login(image_name=image_name)

    primary_tag = image_tags[0]
    primary_image = f"{image_name}:{primary_tag}"
    typer.echo(
        f"Building Docker image once, then pushing tag(s): {', '.join(image_tags)}"
    )
    build_docker_image_only(
        pipeline_dir=pipeline_dir, full_image_name=primary_image
    )

    for tag in image_tags[1:]:
        tagged_image = f"{image_name}:{tag}"
        typer.echo(f"Tagging {primary_image} as {tagged_image}")
        tag_docker_image(source_image=primary_image, target_image=tagged_image)

    for tag in image_tags:
        full_image_name = f"{image_name}:{tag}"
        typer.echo(f"Pushing {full_image_name}...")
        push_docker_image_only(full_image_name=full_image_name)
        typer.echo(f"✅ Docker image '{full_image_name}' pushed successfully.")


def prompt_docker_image_if_missing(pipeline_config: PipelineConfig) -> None:
    """Ensure docker.image_name is set in config.
    - If present: just inform the user and do not prompt.
    - If missing: prompt once, save to config.toml, and confirm.
    """
    image_name = pipeline_config.get("docker", "image_name")

    if image_name:
        typer.echo(f"Using Docker image: {image_name} (tag will be set by version).")
        typer.echo("To change it, edit docker.image_name in config.toml.")
        return

    image_name = typer.prompt("Docker image name (e.g. 'user/pipeline_name')")
    pipeline_config.config.setdefault("docker", {})["image_name"] = image_name
    pipeline_config.save()
    typer.echo(f"Docker image will be: {image_name}:<version>")


VALID_BUMPS = {"patch", "minor", "major", "rc", "final"}


def _read_current_version(cfg: PipelineConfig) -> str:
    try:
        return cfg.get("metadata", "version")
    except KeyError:
        return "0.1.0"


def _to_semver(base: str) -> VersionInfo:
    # strip pre-release for math, normalize to X.Y.Z
    base_only = base.split("-")[0]
    parts = base_only.split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        return VersionInfo.parse(".".join(parts))
    except ValueError:
        return VersionInfo.parse("0.1.0")


def _resolve_bump_choice(bump: Bump | str | None) -> str:
    if bump is None:
        choice = typer.prompt(
            "Choose version bump: patch, minor, major, rc, final", default="patch"
        )
    else:
        # Accept Enum or raw string
        choice = getattr(bump, "value", bump)
    choice = str(choice).strip().lower()
    if choice not in VALID_BUMPS:
        typer.echo("❌ Invalid bump type. Allowed: patch, minor, major, rc, final")
        raise typer.Exit(1)
    return choice


def _apply_bump(ver: VersionInfo, kind: str) -> str:
    if kind == "patch":
        return str(ver.bump_patch())
    if kind == "minor":
        return str(ver.bump_minor())
    if kind == "major":
        return str(ver.bump_major())
    if kind == "rc":
        return f"{ver.bump_patch()}-rc"
    # "final": keep normalized base version (no pre-release)
    return str(ver)


# --- Refactored: low-complexity entrypoint ---
def bump_pipeline_version(
    pipeline_config: PipelineConfig,
    bump: Bump | str | None = None,
) -> str:
    """Bump the pipeline version (semver) and return the new version string."""
    current_version = _read_current_version(pipeline_config)
    typer.echo(f"Current version: {current_version}")

    choice = _resolve_bump_choice(bump)
    new_version = _apply_bump(_to_semver(current_version), choice)

    typer.echo(f"Version bumped to: {new_version}")
    return new_version
