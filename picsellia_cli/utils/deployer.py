import subprocess
from pathlib import Path

import typer

from picsellia_cli.utils.pipeline_config import PipelineConfig


def ensure_docker_login():
    typer.echo("🔐 Checking Docker authentication...")
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, check=True
        )
        if "Username:" not in result.stdout:
            raise RuntimeError("Not logged in to Docker.")
    except Exception as e:
        typer.echo("🔐 You are not logged in to Docker.")
        typer.echo(f"❌ Error: {str(e)}")
        if typer.confirm("Do you want to login now?", default=True):
            try:
                subprocess.run(["docker", "login"], check=True, text=True)
            except subprocess.CalledProcessError:
                typer.echo("❌ Docker login failed.")
                raise typer.Exit()
        else:
            typer.echo("❌ Cannot push image without Docker login.")
            raise typer.Exit()


def build_docker_image_only(pipeline_dir: Path, image_name: str, image_tag: str) -> str:
    pipeline_path = pipeline_dir.resolve()
    dockerfile_path = pipeline_path / "Dockerfile"
    dockerignore_path = pipeline_path / ".dockerignore"
    full_image_name = f"{image_name}:{image_tag}"

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


def build_and_push_docker_image(
    pipeline_dir: Path, image_name: str, image_tag: str, force_login: bool = True
):
    full_image_name = build_docker_image_only(
        pipeline_dir=pipeline_dir, image_name=image_name, image_tag=image_tag
    )

    if force_login:
        ensure_docker_login()

    typer.echo(f"📤 Pushing Docker image '{full_image_name}'...")
    subprocess.run(
        ["docker", "push", full_image_name],
        check=True,
        text=True,
    )
    typer.echo(f"✅ Docker image '{full_image_name}' pushed successfully!")


def prompt_docker_image_if_missing(pipeline_config: PipelineConfig) -> None:
    """
    Interactively prompt user to fill or modify the Docker image section in config.
    Modifies pipeline_config.config['image'] directly.
    """
    image_name = pipeline_config.get("docker", "image_name")
    image_tag = pipeline_config.get("docker", "image_tag")

    if image_name and image_tag:
        typer.echo(f"🔧 Current Docker image: {image_name}:{image_tag}")
        if not typer.confirm(
            "Do you want to keep the current Docker image and tag?", default=True
        ):
            image_name = typer.prompt("📦 Enter Docker image name", default=image_name)
            image_tag = typer.prompt("🏷️ Enter Docker image tag", default=image_tag)
    else:
        if not image_name:
            image_name = typer.prompt("📦 Enter Docker image name")
        if not image_tag:
            image_tag = typer.prompt("🏷️ Enter Docker image tag", default="latest")

    typer.echo(f"🔧 Docker image will be built with: {image_name}:{image_tag}")
    pipeline_config.config["docker"]["image_name"] = image_name
    pipeline_config.config["docker"]["image_tag"] = image_tag
    pipeline_config.save()
