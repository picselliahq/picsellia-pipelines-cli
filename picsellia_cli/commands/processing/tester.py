import os
from typing import Dict

import typer
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError

from picsellia_cli.utils.runner import (
    get_pipeline_data,
    get_global_session,
    create_virtual_env,
    run_pipeline_command,
)
from picsellia_cli.utils.session_manager import session_manager
from picsellia_cli.utils.collect_params import update_processing_parameters

app = typer.Typer(help="Test registered processing pipelines locally.")


def prompt_processing_params(pipeline_name: str, stored_params: Dict) -> Dict:
    input_dataset_version_id = typer.prompt(
        typer.style("📥 Input dataset version ID", fg=typer.colors.CYAN),
        default=stored_params.get("input_dataset_version_id", ""),
    )
    output_dataset_version_name = typer.prompt(
        typer.style("📤 Output dataset version name", fg=typer.colors.CYAN),
        default=stored_params.get(
            "output_dataset_version_name", f"processed_{pipeline_name}"
        ),
    )
    return {
        "input_dataset_version_id": input_dataset_version_id,
        "output_dataset_version_name": output_dataset_version_name,
    }


def check_output_dataset_version(
    client: Client, input_dataset_version_id: str, output_name: str
) -> str:
    try:
        input_dataset_version = client.get_dataset_version_by_id(
            input_dataset_version_id
        )
        dataset = client.get_dataset_by_id(input_dataset_version.origin_id)
        dataset.get_version(version=output_name)

        overwrite = typer.confirm(
            typer.style(
                f"⚠️ A dataset version named '{output_name}' already exists. Overwrite?",
                fg=typer.colors.YELLOW,
            ),
            default=False,
        )
        if overwrite:
            dataset.get_version(version=output_name).delete()
        else:
            output_name = typer.prompt(
                typer.style(
                    "📤 Enter a new output dataset version name", fg=typer.colors.CYAN
                ),
                default=f"{output_name}_new",
            )
    except ResourceNotFoundError:
        pass
    return output_name


@app.command()
def test_pipeline(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the processing pipeline to test"
    ),
):
    pipeline = get_pipeline_data(pipeline_name)
    global_data = get_global_session()
    stored_params = pipeline.get("last_test_params", {})

    params = prompt_processing_params(pipeline_name, stored_params)

    client = Client(
        api_token=global_data["api_token"],
        organization_name=global_data["organization_name"],
    )
    params["output_dataset_version_name"] = check_output_dataset_version(
        client,
        params["input_dataset_version_id"],
        params["output_dataset_version_name"],
    )

    env_path = create_virtual_env(pipeline["requirements_path"])

    repo_root = os.getcwd()
    working_dir = os.path.join(
        repo_root,
        "pipelines",
        pipeline_name,
        "tests",
        params["output_dataset_version_name"],
    )
    os.makedirs(working_dir, exist_ok=True)

    pipeline_script = os.path.join(repo_root, pipeline["local_pipeline_script_path"])
    python_executable = (
        os.path.join(env_path, "bin", "python")
        if os.name != "nt"
        else os.path.join(env_path, "Scripts", "python.exe")
    )

    update_processing_parameters(pipeline_script, pipeline["parameters"])

    command = [
        python_executable,
        pipeline_script,
        "--api_token",
        global_data["api_token"],
        "--organization_name",
        global_data["organization_name"],
        "--working_dir",
        working_dir,
        "--job_type",
        pipeline["pipeline_type"],
        "--input_dataset_version_id",
        params["input_dataset_version_id"],
        "--output_dataset_version_name",
        params["output_dataset_version_name"],
    ]

    run_pipeline_command(command, working_dir)

    pipeline["last_test_params"] = params
    session_manager.add_pipeline(pipeline_name, pipeline)
    typer.echo(
        typer.style(
            f"✅ Processing pipeline '{pipeline_name}' tested successfully!",
            fg=typer.colors.GREEN,
            bold=True,
        )
    )


if __name__ == "__main__":
    app()
