import os
import subprocess
import typer


def create_virtual_env(requirements_path: str) -> str:
    pipeline_dir = os.path.dirname(requirements_path)
    env_path = os.path.join(pipeline_dir, ".venv")
    python_path = os.path.join(env_path, "bin", "python3")

    if requirements_path.endswith("pyproject.toml"):
        typer.echo("📦 Detected pyproject.toml — using uv sync...")

        try:
            subprocess.run(["uv", "sync"], cwd=pipeline_dir, check=True, text=True)

            typer.echo("➕ Ensuring picsellia-cv-engine is added...")
            subprocess.run(
                [
                    "uv",
                    "add",
                    "git+https://github.com/picselliahq/picsellia-cv-engine.git@main",
                ],
                cwd=pipeline_dir,
                check=True,
                text=True,
            )

        except subprocess.CalledProcessError as e:
            typer.secho(
                f"❌ uv operation failed (code {e.returncode})", fg=typer.colors.RED
            )
            raise typer.Exit(code=e.returncode)

    elif requirements_path.endswith(".txt"):
        if not os.path.exists(env_path):
            typer.echo("⚙️ Creating virtual environment with uv...")
            subprocess.run(["uv", "venv"], cwd=pipeline_dir, check=True, text=True)

        typer.echo(f"📦 Installing dependencies from {requirements_path}...")
        subprocess.run(
            ["uv", "pip", "install", "--python", python_path, "-r", requirements_path],
            check=True,
            text=True,
        )

        typer.echo("➕ Installing picsellia-cv-engine from GitHub...")
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                python_path,
                "git+https://github.com/picselliahq/picsellia-cv-engine.git@main",
            ],
            check=True,
            text=True,
        )
    else:
        typer.secho("❌ Unsupported requirements format.", fg=typer.colors.RED)
        raise typer.Exit()

    return os.path.join(os.getcwd(), pipeline_dir, ".venv")


def run_pipeline_command(command: list[str], working_dir: str):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(os.getcwd())

    typer.echo(
        f"🚀 Running pipeline with working_dir={working_dir} and PYTHONPATH={os.getcwd()}..."
    )

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
