import subprocess
import sys
from pathlib import Path

import typer

from picsellia_cli.utils.pipeline_config import PipelineConfig
from semver import VersionInfo


def ensure_docker_login(image_name: str):
    """
    Ensure Docker is logged in as the correct user based on image_name (e.g., 'user/image').
    If not, logs out and prompts for login with the expected user.
    """
    expected_user = image_name.split("/")[0]
    typer.echo("🔐 Checking Docker authentication (via `docker info`)...")

    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            check=True,
            stdin=sys.stdin,
        )
    except subprocess.CalledProcessError:
        typer.echo("❌ Failed to retrieve Docker info. Is Docker running?")
        raise typer.Exit()

    current_user = None
    for line in result.stdout.splitlines():
        if line.find("Username:") != -1:
            current_user = line.split(":", 1)[1].strip()
            break

    if current_user != expected_user:
        if current_user:
            typer.echo(
                f"⚠️  Logged in as: '{current_user}', but expected: '{expected_user}'"
            )
        else:
            typer.echo("🔐 No Docker user currently logged in.")

        typer.echo(f"🔁 Re-authenticating with Docker Hub as '{expected_user}'...")
        typer.echo("🚪 Logging out...")
        subprocess.run(["docker", "logout"], check=True)

        typer.echo(
            f"🔑 Logging in as '{expected_user}' (you may need to enter a Personal Access Token)"
        )
        try:
            subprocess.run(
                ["docker", "login", "-u", expected_user],
                check=True,
                stdin=sys.stdin,
            )
        except subprocess.CalledProcessError:
            typer.echo("❌ Docker login failed. Please check your credentials.")
            raise typer.Exit()
    else:
        typer.echo(f"✅ Docker already logged in as expected user: '{expected_user}'")


def build_docker_image_only(pipeline_dir: Path, full_image_name: str) -> str:
    pipeline_path = pipeline_dir.resolve()
    dockerfile_path = pipeline_path / "Dockerfile"
    dockerignore_path = pipeline_path / ".dockerignore"

    if not pipeline_path.exists():
        typer.echo(f"⚠️ Pipeline directory '{pipeline_dir}' not found.")
        raise typer.Exit()

    if not dockerfile_path.exists():
        typer.echo(f"⚠️ Missing Dockerfile in '{pipeline_dir}'.")
        raise typer.Exit()

    if not dockerignore_path.exists():
        dockerignore_path.write_text(
            ".venv/\nvenv/\n__pycache__/\n*.pyc\n*.pyo\n.DS_Store\n"
        )

    typer.echo(f"🚀 Building Docker image '{full_image_name}'...")
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
        raise typer.Exit(code=e.returncode)

    return full_image_name


def push_docker_image_only(full_image_name: str):
    subprocess.run(
        ["docker", "push", full_image_name],
        check=True,
        text=True,
    )


def build_and_push_docker_image(
    pipeline_dir: Path, image_name: str, image_tags: list[str], force_login: bool = True
):
    if force_login:
        ensure_docker_login(image_name=image_name)

    for tag in image_tags:
        full_image_name = f"{image_name}:{tag}"
        typer.echo(f"🐳 Building and pushing image: {full_image_name}")
        build_docker_image_only(
            pipeline_dir=pipeline_dir, full_image_name=full_image_name
        )
        push_docker_image_only(full_image_name=full_image_name)
        typer.echo(f"✅ Docker image '{full_image_name}' pushed successfully!")


def prompt_docker_image_if_missing(pipeline_config: PipelineConfig) -> None:
    """
    Prompt the user to set or confirm the Docker image name (without tag).
    Only modifies 'docker.image_name' in the pipeline config.
    """
    image_name = pipeline_config.get("docker", "image_name")

    if image_name:
        typer.echo(
            f"🔧 Current Docker image: {image_name} (tag will be set by version)"
        )
        if not typer.confirm("Do you want to keep this image name?", default=True):
            image_name = typer.prompt(
                "📦 Enter Docker image name (e.g. 'user/pipeline_name', tag will be set by version)"
            )
    else:
        image_name = typer.prompt(
            "📦 Enter Docker image name (e.g. 'user/pipeline_name', tag will be set by version)"
        )

    pipeline_config.config["docker"]["image_name"] = image_name
    pipeline_config.save()
    typer.echo(f"✅ Docker image will be: {image_name}:<version>")


def bump_pipeline_version(pipeline_config: PipelineConfig):
    try:
        current_version = pipeline_config.get("metadata", "version")
    except KeyError:
        current_version = "0.1.0"

    typer.echo(f"📌 Current version: {current_version}")

    bump_type = typer.prompt(
        "🔁 Choose version bump: patch, minor, major, rc, final",
        default="patch",
    )

    try:
        base_version = current_version.split("-")[0]
        # Patch: normalize to MAJOR.MINOR.PATCH
        parts = base_version.split(".")
        while len(parts) < 3:
            parts.append("0")
        normalized = ".".join(parts)

        version = VersionInfo.parse(normalized)
    except ValueError:
        version = VersionInfo.parse("0.1.0")

    if bump_type == "patch":
        new_version = version.bump_patch()
    elif bump_type == "minor":
        new_version = version.bump_minor()
    elif bump_type == "major":
        new_version = version.bump_major()
    elif bump_type == "rc":
        new_version = f"{version.bump_patch()}-rc"
    elif bump_type == "final":
        new_version = str(version)
    else:
        raise typer.Exit("❌ Invalid bump type")

    typer.echo(f"✅ Version bumped to: {new_version}")

    return new_version
