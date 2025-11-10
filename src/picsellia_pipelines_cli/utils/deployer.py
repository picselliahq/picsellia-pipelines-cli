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


def ensure_docker_login(image_name: str):
    """
    Ensure Docker auth is set for the target image's registry.

    - For images with an explicit registry (e.g., 'ghcr.io/...', '0c6y...ovh.net/...'):
        * Always attempt: `docker logout <registry>` (ignore errors)
        * Then interactive: `docker login <registry>`
    - For Docker Hub (no explicit registry in image):
        * Read the Username from `docker info`
        * If it differs from the expected namespace (first path segment),
          do `docker logout` then `docker login -u <expected_user>`

    Notes:
      * `docker info` only shows the Docker Hub username, not per-registry logins.
      * This function is interactive when credentials are needed.
    """
    registry = _detect_registry_host(image_name)

    if registry:
        typer.echo(f"Detected registry: {registry}")
        try:
            subprocess.run(["docker", "logout", registry], check=False, text=True)
        except Exception:
            pass

        typer.echo(f"Logging in to registry '{registry}' …")
        try:
            subprocess.run(
                ["docker", "login", registry],
                check=True,
                text=True,
                stdin=sys.stdin,  # allow interactive username/password
            )
        except subprocess.CalledProcessError as err:
            typer.echo("❌ Docker registry login failed.")
            raise typer.Exit(1) from err

        typer.echo(f"✓ Logged in to {registry}")
        return

    # ── Docker Hub (implicit) ────────────────────────────────────────────────
    expected_user = image_name.split("/", 1)[0]
    typer.echo("Checking Docker authentication (via `docker info`)…")
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            check=True,
            stdin=sys.stdin,
        )
    except subprocess.CalledProcessError as err:
        typer.echo("Failed to retrieve Docker info. Is Docker running?")
        raise typer.Exit(1) from err

    current_user = None
    for line in result.stdout.splitlines():
        if "Username:" in line:
            current_user = line.split(":", 1)[1].strip()
            break

    if current_user == expected_user:
        typer.echo(f"Docker Hub already logged in as expected user: '{expected_user}'")
        return

    if current_user:
        typer.echo(f"Logged in as: '{current_user}', but expected: '{expected_user}'")
    else:
        typer.echo("No Docker Hub user currently logged in.")

    typer.echo(f"Re-authenticating on Docker Hub as '{expected_user}'…")
    # Logout of Docker Hub (no registry arg logs out of Hub)
    subprocess.run(["docker", "logout"], check=False, text=True)

    try:
        subprocess.run(
            ["docker", "login", "-u", expected_user],
            check=True,
            text=True,
            stdin=sys.stdin,  # interactive password/token
        )
    except subprocess.CalledProcessError as err:
        typer.echo("❌ Docker Hub login failed. Please check your credentials.")
        raise typer.Exit(1) from err

    typer.echo(f"✓ Logged in to Docker Hub as '{expected_user}'")


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

    typer.echo(f"Building Docker image '{full_image_name}'...")
    try:
        subprocess.run(
            ["docker", "build", "-t", full_image_name, "-f", dockerfile_path, "."],
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

    Args:
        pipeline_dir: Directory containing the Dockerfile.
        image_name: Base image name (without tag).
        image_tags: List of tags to build and push.
        force_login: If True, ensure Docker authentication before building.
    """
    image_name = _validate_registry_path(image_name)

    if force_login:
        ensure_docker_login(image_name=image_name)

    for tag in image_tags:
        full_image_name = f"{image_name}:{tag}"
        typer.echo(f"Building and pushing image: {full_image_name}")
        build_docker_image_only(
            pipeline_dir=pipeline_dir, full_image_name=full_image_name
        )
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
