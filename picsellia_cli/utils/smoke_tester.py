import subprocess
import typer
import os
from shlex import quote  # 👈 pour échapper correctement les args shell
from picsellia_cli.utils.logging import bullet, hr


def run_smoke_test_container(
    image: str, command: list[str], env_vars: dict, pipeline_name: str
):
    container_name = "smoke-test-temp"

    log_cmd = f"source /experiment/{pipeline_name}/.venv/bin/activate &&" + " ".join(
        quote(arg) for arg in command
    )

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
        "--gpus",
        "all",
        "--shm-size",
        "8g",
        "--name",
        container_name,
        "--entrypoint",
        "bash",
        "-v",
        f"{os.getcwd()}:/workspace",
    ]

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
