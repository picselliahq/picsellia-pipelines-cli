import subprocess
import typer
import os
from shlex import quote
from picsellia_cli.utils.logging import bullet, hr


def run_smoke_test_container(
    image: str,
    command: list[str],
    env_vars: dict,
    pipeline_name: str,
    use_gpu: bool = False,
):
    """Run a smoke test container for the pipeline.

    Args:
        image: Full Docker image name.
        command: Command to run inside the container.
        env_vars: Environment variables to pass.
        pipeline_name: Pipeline name (used to locate venv).
        use_gpu: Whether to request GPU access with `--gpus all`.
    """
    container_name = "smoke-test-temp"

    log_cmd = f"source /experiment/{pipeline_name}/.venv/bin/activate && " + " ".join(
        quote(arg) for arg in command
    )

    # Clean up any previous container
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    docker_command = [
        "docker",
        "run",
        "--shm-size",
        "8g",
        "--name",
        container_name,
        "--entrypoint",
        "bash",
        "-v",
        f"{os.getcwd()}:/workspace",
    ]

    # Add GPU flag if requested
    if use_gpu:
        if check_nvidia_runtime():
            docker_command.insert(2, "--gpus")
            docker_command.insert(3, "all")
        else:
            typer.echo("❌ GPU requested but NVIDIA runtime not available.")
            raise typer.Exit(1)

    # Add env vars
    for k, v in env_vars.items():
        docker_command += ["-e", f"{k}={v}"]

    docker_command += [image, "-c", log_cmd]

    bullet("Launching Docker training container…", accent=True)
    proc = subprocess.Popen(
        docker_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    triggered = False
    if proc.stdout is None:
        typer.echo("❌ Failed to capture Docker logs.")
        return

    try:
        for line in proc.stdout:
            print(line, end="")
            if "--ec-- 1" in line:
                typer.echo(
                    "\n❌ '--ec-- 1' detected! Something went wrong during training."
                )
                typer.echo(
                    "📥 Copying training logs before stopping the container...\n"
                )
                triggered = True

                subprocess.run(
                    [
                        "docker",
                        "cp",
                        f"{container_name}:/experiment/training.log",
                        "training.log",
                    ],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                subprocess.run(["docker", "stop", container_name], check=False)
                break
    except Exception as e:
        typer.echo(f"❌ Error while monitoring Docker: {e}")
    finally:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            typer.echo("⚠️ Timeout reached. Killing process.")
            proc.kill()

    print(f"\n🚦 Docker container exited with code: {proc.returncode}")

    if triggered or proc.returncode != 0:
        typer.echo("\n🧾 Captured training.log content:\n" + "-" * 60)
        try:
            with open("training.log") as f:
                print(f.read())
        except Exception as e:
            typer.echo(f"⚠️ Could not read training.log: {e}")
        print("-" * 60 + "\n")
    else:
        typer.echo("✅ Docker pipeline ran successfully.")

    hr()


def check_nvidia_runtime() -> bool:
    """Check if the NVIDIA runtime is available in Docker."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if line.strip().startswith("Runtimes:"):
                if "nvidia" in line:
                    return True
                typer.echo(
                    "⚠NVIDIA runtime not found in Docker.\n"
                    "To enable GPU support, install NVIDIA Container Toolkit:\n"
                    "  sudo apt-get install -y nvidia-container-toolkit\n"
                    "  sudo nvidia-ctk runtime configure --runtime=docker\n"
                    "  sudo systemctl restart docker\n\n"
                    "Then verify with:\n"
                    "  docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi\n"
                )
                return False
        typer.echo("⚠️ Could not find a 'Runtimes:' line in `docker info` output.")
        return False
    except Exception as e:
        typer.echo(f"⚠️ Could not verify Docker runtime: {e}")
        return False
