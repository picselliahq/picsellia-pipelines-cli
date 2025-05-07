import os
import subprocess
import venv
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
    env_path = os.path.join(os.path.dirname(requirements_path), ".venv")
    pip_executable = (
        os.path.join(env_path, "bin", "pip")
        if os.name != "nt"
        else os.path.join(env_path, "Scripts", "pip.exe")
    )

    if not os.path.exists(env_path):
        typer.echo(f"⚙️ Creating virtual environment at {env_path}...")
        venv.create(env_path, with_pip=True)

    if os.path.exists(requirements_path):
        typer.echo(f"📦 Installing dependencies from {requirements_path}...")
        subprocess.run([pip_executable, "install", "-r", requirements_path], check=True)
    else:
        typer.echo("⚠️ No requirements.txt found, skipping dependency installation.")

    typer.echo("📦 Installing picsellia-cv-engine from GitHub...")
    subprocess.run(
        [
            pip_executable,
            "install",
            "git+https://github.com/picselliahq/picsellia-cv-engine.git@main",
        ],
        check=True,
    )

    return env_path


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
        typer.echo(typer.style(str(e), fg=typer.colors.RED))
        raise typer.Exit(code=e.returncode)
