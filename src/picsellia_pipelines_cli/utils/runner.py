import os
import subprocess
from pathlib import Path

import typer


def create_virtual_env(requirements_path: Path) -> Path:
    requirements_path = Path(requirements_path).resolve()
    pipeline_dir = requirements_path.parent
    env_path = pipeline_dir / ".venv"
    python_path = (
        env_path / "bin" / "python3"
        if os.name != "nt"
        else env_path / "Scripts" / "python.exe"
    )

    if requirements_path.name == "pyproject.toml":
        typer.echo("📦 Detected pyproject.toml — using uv sync...")

        try:
            subprocess.run(
                ["uv", "lock", "--no-cache", "--project", str(pipeline_dir)], check=True
            )
            subprocess.run(
                ["uv", "sync", "--no-cache", "--project", str(pipeline_dir)], check=True
            )
        except subprocess.CalledProcessError as e:
            typer.secho(
                f"❌ uv operation failed (code {e.returncode})", fg=typer.colors.RED
            )
            raise typer.Exit(code=e.returncode)

    elif requirements_path.suffix == ".txt":
        if not env_path.exists():
            typer.echo("⚙️ Creating virtual environment with uv...")
            subprocess.run(["uv", "venv"], cwd=str(pipeline_dir), check=True, text=True)

        typer.echo(f"📦 Installing dependencies from {requirements_path}...")
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python_path),
                "-r",
                str(requirements_path),
            ],
            check=True,
            text=True,
        )
    else:
        typer.secho("❌ Unsupported requirements format.", fg=typer.colors.RED)
        raise typer.Exit()

    return env_path


def run_pipeline_command(command: list[str], api_token: str):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    env["api_token"] = api_token

    typer.echo("🚀 Running pipeline...")

    try:
        subprocess.run(
            command,
            check=True,
            env=env,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        typer.echo(
            typer.style(
                "\n❌ Pipeline execution failed.", fg=typer.colors.RED, bold=True
            )
        )
        typer.echo("🔍 Most recent error output:\n")
        typer.echo(f"🔴 Error details:\n{e.stderr}")
        raise typer.Exit(code=e.returncode)
