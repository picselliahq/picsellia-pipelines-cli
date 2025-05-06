import os
import subprocess
from typing import Dict

import typer
from picsellia_cli.utils.session_manager import session_manager


def ensure_docker_login():
    typer.echo("🔐 Checking Docker authentication...")
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, check=True
        )
        if "Username:" not in result.stdout:
            raise RuntimeError("Not logged in to Docker.")
    except Exception:
        typer.echo("🔐 You are not logged in to Docker.")
        if typer.confirm("Do you want to login now?", default=True):
            subprocess.run(["docker", "login"], check=True)
        else:
            typer.echo("❌ Cannot push image without Docker login.")
            raise typer.Exit()


def build_and_push_docker_image(
    pipeline_dir: str, image_name: str, image_tag: str, force_login: bool = False
):
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
    subprocess.run(
        ["docker", "build", "-t", full_image_name, "-f", dockerfile_path, "."],
        cwd=pipeline_dir,
        check=True,
    )

    if force_login:
        ensure_docker_login()

    typer.echo(f"📤 Pushing Docker image '{full_image_name}'...")
    subprocess.run(["docker", "push", full_image_name], check=True)

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
    if not pipeline_data.get("image_name") or not pipeline_data.get("image_tag"):
        pipeline_data["image_name"] = typer.prompt("📦 Enter Docker image name")
        pipeline_data["image_tag"] = typer.prompt(
            "🏷️ Enter Docker image tag", default="latest"
        )
        session_manager.add_pipeline(pipeline_name, pipeline_data)
    return pipeline_data
