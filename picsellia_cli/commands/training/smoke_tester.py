import os
import subprocess

import typer

from picsellia_cli.utils.deployer import build_docker_image_only
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer(help="Run a smoke test for a training pipeline using Docker.")


@app.command()
def smoke_test(
    pipeline_name: str = typer.Argument(...),
    experiment_id: str = typer.Option(...),
    image_tag: str = typer.Option("latest"),
):
    session_manager.ensure_session_initialized()
    pipeline_data = session_manager.get_pipeline(pipeline_name)

    if not pipeline_data:
        typer.echo(f"❌ Pipeline '{pipeline_name}' not found.")
        raise typer.Exit()

    if not pipeline_data.get("image_name"):
        pipeline_data["image_name"] = typer.prompt("📦 Enter Docker image name")

    if not pipeline_data.get("image_tag"):
        pipeline_data["image_tag"] = image_tag or typer.prompt(
            "🏷️ Enter Docker image tag", default="latest"
        )

    session_manager.add_pipeline(pipeline_name, pipeline_data)

    full_image_name = f"{pipeline_data['image_name']}:{pipeline_data['image_tag']}"

    repo_root = os.getcwd()
    pipeline_dir = os.path.join(repo_root, "pipelines", pipeline_name)

    build_docker_image_only(
        pipeline_dir=pipeline_dir,
        image_name=pipeline_data["image_name"],
        image_tag=pipeline_data["image_tag"],
    )

    global_data = session_manager.get_global_session()
    if global_data is None:
        typer.echo("❌ No global session found.")
        raise typer.Exit()

    env_vars = {
        "api_token": global_data["api_token"],
        "organization_name": global_data["organization_name"],
        "experiment_id": experiment_id,
        "DEBUG": "True",
    }

    script_path = pipeline_data.get(
        "picsellia_pipeline_script_path",
        f"pipelines/{pipeline_name}/training_pipeline.py",
    )

    run_smoke_test_container(
        image=full_image_name, script=script_path, env_vars=env_vars
    )


def run_smoke_test_container(image: str, script: str, env_vars: dict):
    container_name = "smoke-test-temp"
    log_cmd = f"run python3.10 {script}"

    # Clean up old container if needed
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    docker_command = [
        "docker",
        "run",
        "--name",
        container_name,
        "--entrypoint",
        "bash",
        "-v",
        f"{os.getcwd()}:/workspace",
    ]

    for key, value in env_vars.items():
        docker_command += ["-e", f"{key}={value}"]

    docker_command += [image, "-c", log_cmd]

    typer.echo("🚀 Launching Docker training container...\n")

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

                # Copy from /experiment instead of /workspace
                subprocess.run(
                    [
                        "docker",
                        "cp",
                        f"{container_name}:/experiment/training.log",
                        "training.log",
                    ],
                    check=True,
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
