import os
import subprocess
from typing import Dict

import typer
from picsellia_cli.utils.session_manager import session_manager


def ensure_docker_login():
    typer.echo("🔐 Checking Docker authentication...")
    try:
        result = subprocess.run(
            ["docker", "info"],
            text=True,
            check=True,
        )
        if "Username:" not in result.stdout:
            raise RuntimeError("Not logged in to Docker.")
    except Exception as e:
        typer.echo("🔐 You are not logged in to Docker.")
        typer.echo(f"❌ Error: {str(e)}")
        if typer.confirm("Do you want to login now?", default=True):
            try:
                subprocess.run(
                    ["docker", "login"],
                    check=True,
                    text=True,
                )
            except subprocess.CalledProcessError as login_error:
                typer.echo(f"❌ Docker login failed: {login_error.stderr}")
                raise typer.Exit()
        else:
            typer.echo("❌ Cannot push image without Docker login.")
            raise typer.Exit()


def build_docker_image_only(pipeline_dir: str, image_name: str, image_tag: str):
    full_image_name = f"{image_name}:{image_tag}"

    if not os.path.exists(pipeline_dir):
        typer.echo(f"⚠️ Pipeline directory '{pipeline_dir}' not found.")
        raise typer.Exit()

    dockerfile_path = os.path.join(pipeline_dir, "Dockerfile")
    dockerignore_path = os.path.join(pipeline_dir, ".dockerignore")

    if not os.path.exists(dockerfile_path):
        typer.echo(f"⚠️ Missing Dockerfile in '{pipeline_dir}'.")
        raise typer.Exit()

    if not os.path.exists(dockerignore_path):
        with open(dockerignore_path, "w") as f:
            f.write(".venv/\nvenv/\n__pycache__/\n*.pyc\n*.pyo\n.DS_Store\n")

    typer.echo(f"🚀 Building Docker image '{full_image_name}'...")
    try:
        result = subprocess.run(
            ["docker", "build", "-t", full_image_name, "-f", dockerfile_path, "."],
            cwd=pipeline_dir,
            check=True,
            text=True,
        )
        typer.echo(result.stdout)

    except subprocess.CalledProcessError as e:
        typer.echo(
            typer.style(
                f"\n❌ Failed to build Docker image. Command failed with exit code {e.returncode}.",
                fg=typer.colors.RED,
                bold=True,
            )
        )
        typer.echo(f"🔍 Error details:\n{e.stderr}")
        raise typer.Exit(code=e.returncode)

    return full_image_name


def build_and_push_docker_image(
    pipeline_dir: str, image_name: str, image_tag: str, force_login: bool = False
):
    full_image_name = build_docker_image_only(pipeline_dir, image_name, image_tag)

    if force_login:
        ensure_docker_login()

    typer.echo(f"📤 Pushing Docker image '{full_image_name}'...")
    subprocess.run(
        ["docker", "push", full_image_name],
        check=True,
        text=True,
    )

    typer.echo(f"✅ Docker image '{full_image_name}' pushed successfully!")


def get_pipeline_data(pipeline_name: str) -> Dict:
    session_manager.ensure_session_initialized()
    pipeline_data = session_manager.get_pipeline(pipeline_name)
    if not pipeline_data:
        typer.echo(
            typer.style(
                f"❌ Pipeline '{pipeline_name}' not found. Run `pipeline-cli list`.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit()
    return pipeline_data


def prompt_docker_image_if_missing(pipeline_name: str, pipeline_data: Dict) -> Dict:
    if pipeline_data.get("image_name") and pipeline_data.get("image_tag"):
        current_image = pipeline_data["image_name"]
        current_tag = pipeline_data["image_tag"]

        typer.echo(f"🔧 Current Docker image: {current_image}:{current_tag}")

        no_change_image = typer.confirm(
            "Do you want to keep the current Docker image and tag?",
            default=True,
        )

        if not no_change_image:
            pipeline_data["image_name"] = typer.prompt(
                "📦 Enter Docker image name", default=current_image
            )
            pipeline_data["image_tag"] = typer.prompt(
                "🏷️ Enter Docker image tag", default=current_tag
            )

    else:
        if not pipeline_data.get("image_name"):
            pipeline_data["image_name"] = typer.prompt("📦 Enter Docker image name")

        if not pipeline_data.get("image_tag"):
            pipeline_data["image_tag"] = typer.prompt(
                "🏷️ Enter Docker image tag", default="latest"
            )

    typer.echo(
        f"🔧 Docker image will be built with: {pipeline_data['image_name']}:{pipeline_data['image_tag']}"
    )

    session_manager.update_pipeline(name=pipeline_name, data=pipeline_data)

    return pipeline_data
