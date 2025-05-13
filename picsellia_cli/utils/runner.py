import os
import subprocess
from typing import Dict

import typer
from picsellia_cli.utils.session_manager import session_manager


def get_pipeline_data(pipeline_name: str) -> Dict:
    session_manager.ensure_session_initialized()
    pipeline = session_manager.get_pipeline(pipeline_name)
    if not pipeline:
        typer.echo(
            typer.style(
                f"❌ Pipeline '{pipeline_name}' not found. Run `pipeline-cli list`.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit()
    return pipeline


def get_global_session() -> Dict:
    global_data = session_manager.get_global_session()
    if not global_data:
        typer.echo(
            typer.style(
                "❌ Global session not initialized. Run `pipeline-cli init` first.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit()
    return global_data


def create_virtual_env(requirements_path: str) -> str:
    pipeline_dir = os.path.dirname(requirements_path)
    env_path = os.path.join(pipeline_dir, ".venv")

    if not os.path.exists(env_path):
        typer.echo("⚙️ Creating virtual environment with uv...")
        try:
            subprocess.run(
                ["uv", "venv"],
                cwd=pipeline_dir,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            typer.echo(
                typer.style(
                    f"❌ Failed to create virtual environment. Command failed with exit code {e.returncode}.",
                    fg=typer.colors.RED,
                    bold=True,
                )
            )
            typer.echo(f"🔍 Error details:\n{e.stderr}")
            raise typer.Exit(code=e.returncode)
    try:
        typer.echo("📦 Installing dependencies using uv...")

        result = subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                os.path.join(env_path, "bin", "python3"),
                "-r",
                requirements_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        typer.echo(result.stdout)

    except subprocess.CalledProcessError as e:
        typer.echo(
            typer.style(
                f"\n❌ Failed to install dependencies with uv. Command failed with exit code {e.returncode}.",
                fg=typer.colors.RED,
                bold=True,
            )
        )
        typer.echo(f"🔍 Error details:\n{e.stderr}")
        raise typer.Exit(code=e.returncode)

    try:
        typer.echo("📦 Installing picsellia-cv-engine from GitHub...")
        result = subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                os.path.join(env_path, "bin", "python3"),
                "git+https://github.com/picselliahq/picsellia-cv-engine.git@main",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        typer.echo(result.stdout)

    except subprocess.CalledProcessError as e:
        typer.echo(
            typer.style(
                f"\n❌ Failed to install picsellia-cv-engine. Command failed with exit code {e.returncode}.",
                fg=typer.colors.RED,
                bold=True,
            )
        )
        typer.echo(f"🔍 Error details:\n{e.stderr}")
        raise typer.Exit(code=e.returncode)

    return os.path.join(os.getcwd(), pipeline_dir, ".venv")


def run_pipeline_command(command: list[str], working_dir: str):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(os.getcwd())

    typer.echo(
        f"🚀 Running pipeline with working_dir={working_dir} and PYTHONPATH={os.getcwd()}..."
    )

    try:
        subprocess.run(command, check=True, env=env)
    except subprocess.CalledProcessError as e:
        typer.echo(
            typer.style(
                "\n❌ Pipeline execution failed.", fg=typer.colors.RED, bold=True
            )
        )
        typer.echo("🔍 Most recent error output:\n")
        typer.echo(f"🔴 Error details:\n{e.stderr}")
        raise typer.Exit(code=e.returncode)
