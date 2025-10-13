import os
import subprocess
from pathlib import Path
from shlex import quote

import typer

from picsellia_pipelines_cli.utils.deployer import build_docker_image_only
from picsellia_pipelines_cli.utils.logging import bullet, hr, kv, section
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig
from picsellia_pipelines_cli.utils.tester import build_pipeline_command


def _docker_rm(container_name: str) -> None:
    """Remove container if it exists (best-effort)."""
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        check=False,
        text=True,
        capture_output=True,
    )


def _ensure_gpu_available_or_exit() -> None:
    """Exit with a clear message if NVIDIA runtime isn't available."""
    if not check_nvidia_runtime():
        typer.echo("❌ GPU requested but NVIDIA runtime not available.")
        raise typer.Exit(1)


def _compose_docker_run_cmd(
    image: str,
    container_name: str,
    command: list[str],
    env_vars: dict,
    use_gpu: bool,
    workdir: str,
    pipeline_name: str,
) -> list[str]:
    """Build the final `docker run` command with envs, volume, GPU, and entrypoint."""
    # prepare shell command to run inside the container (activate venv + user cmd)
    log_cmd = f"source /experiment/{pipeline_name}/.venv/bin/activate && " + " ".join(
        quote(arg) for arg in command
    )

    base = [
        "docker",
        "run",
        "--shm-size",
        "8g",
        "--name",
        container_name,
    ]

    if use_gpu:
        base += ["--gpus", "all"]

    base += [
        "--entrypoint",
        "bash",
        "-v",
        f"{workdir}:/workspace",
    ]

    # env variables
    for k, v in env_vars.items():
        base += ["-e", f"{k}={v}"]

    # image + bash -c "<log_cmd>"
    base += [image, "-c", log_cmd]
    return base


def _stream_container_logs_and_detect_error(
    proc: subprocess.Popen, container_name: str
) -> tuple[bool, int]:
    """Stream logs; detect '--ec-- 1'; copy training.log and stop container if seen.

    Returns:
        (triggered, returncode)
        - triggered: True if '--ec-- 1' encountered and handled
        - returncode: docker process return code
    """
    triggered = False

    if proc.stdout is None:
        typer.echo("❌ Failed to capture Docker logs.")
        proc.wait(timeout=10)
        return triggered, proc.returncode or 1

    try:
        for line in proc.stdout:
            print(line, end="")
            if "--ec-- 1" in line and not triggered:
                typer.echo(
                    "\n❌ '--ec-- 1' detected! Something went wrong during training."
                )
                typer.echo(
                    "📥 Copying training logs before stopping the container...\n"
                )
                triggered = True

                # best-effort copy of training.log, prefer capture_output to PIPE
                subprocess.run(
                    [
                        "docker",
                        "cp",
                        f"{container_name}:/experiment/training.log",
                        "training.log",
                    ],
                    check=False,
                    text=True,
                    capture_output=True,
                )
                subprocess.run(["docker", "stop", container_name], check=False)
                # we break once we've handled the error marker
                break
    except Exception as e:
        typer.echo(f"❌ Error while monitoring Docker: {e}")
    finally:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            typer.echo("⚠️ Timeout reached. Killing process.")
            proc.kill()

    return triggered, proc.returncode or 0


def _print_captured_training_log_if_any(error_or_triggered: bool) -> None:
    """If there was an error, try to print the local training.log content."""
    if not error_or_triggered:
        return

    typer.echo("\n🧾 Captured training.log content:\n" + "-" * 60)
    try:
        with open("training.log") as f:
            print(f.read())
    except Exception as e:
        typer.echo(f"⚠️ Could not read training.log: {e}")
    print("-" * 60 + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# Main smoke-test entry
# ──────────────────────────────────────────────────────────────────────────────


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

    # optional GPU check early to fail fast
    if use_gpu:
        _ensure_gpu_available_or_exit()

    # clean previous container
    _docker_rm(container_name)

    # build docker run command
    docker_command = _compose_docker_run_cmd(
        image=image,
        container_name=container_name,
        command=command,
        env_vars=env_vars,
        use_gpu=use_gpu,
        workdir=os.getcwd(),
        pipeline_name=pipeline_name,
    )

    bullet("Launching Docker container…", accent=True)
    try:
        proc = subprocess.Popen(
            docker_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
    except Exception as e:
        typer.echo(f"❌ Failed to start Docker process: {e}")
        raise typer.Exit(1) from e

    triggered, returncode = _stream_container_logs_and_detect_error(
        proc, container_name
    )

    print(f"\nDocker container exited with code: {returncode}")

    _print_captured_training_log_if_any(triggered or returncode != 0)

    if not triggered and returncode == 0:
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


def prepare_docker_image(pipeline_config: PipelineConfig) -> str:
    image_name = pipeline_config.get("docker", "image_name")
    image_tag = "test"
    full_image_name = f"{image_name}:{image_tag}"

    section("🐳 Docker image")
    kv("Image", image_name)
    kv("Tag", image_tag)

    build_docker_image_only(
        pipeline_dir=pipeline_config.pipeline_dir,
        full_image_name=full_image_name,
    )
    return full_image_name


def build_smoke_command(
    pipeline_name: str,
    pipeline_config: PipelineConfig,
    run_config_path: Path,
    python_version: str,
) -> list[str]:
    pipeline_script = (
        f"{pipeline_name}/{pipeline_config.get('execution', 'pipeline_script')}"
    )
    python_bin = f"python{python_version}"
    pipeline_script_path = Path(pipeline_script)

    return build_pipeline_command(
        python_executable=Path(python_bin),
        pipeline_script_path=pipeline_script_path,
        run_config_file=run_config_path,
        mode="local",
    )


def build_env_vars(
    env_config: dict, run_config: dict, include_experiment: bool = False
) -> dict:
    vars = {
        "api_token": env_config["api_token"],
        "organization_name": run_config["auth"]["organization_name"],
        "host": run_config["auth"]["host"],
        "DEBUG": "True",
    }
    if include_experiment:
        vars["experiment_id"] = run_config["output"]["experiment"]["id"]
    return vars
