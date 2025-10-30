import typer

from picsellia_pipelines_cli.commands.processing.utils.tester import (
    check_output_dataset_version,
    enrich_output_metadata_after_run,
    enrich_run_config_with_metadata,
    get_processing_params,
)
from picsellia_pipelines_cli.utils.initializer import init_client
from picsellia_pipelines_cli.utils.logging import kv, section
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig
from picsellia_pipelines_cli.utils.run_manager import RunManager
from picsellia_pipelines_cli.utils.tester import (
    load_or_init_run_config,
    prepare_auth_and_env,
    prepare_python_executable,
    resolve_run_config_path,
    run_pipeline,
    save_and_get_run_config_path,
    select_run_dir,
)


def test_processing(
    pipeline_name: str,
    run_config_file: str | None = None,
    reuse_dir: bool = False,
):
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)
    pipeline_type = pipeline_config.get("metadata", "type")
    run_manager = RunManager(pipeline_dir=pipeline_config.pipeline_dir)

    run_dir = select_run_dir(run_manager=run_manager, reuse_dir=reuse_dir)
    run_config_path = resolve_run_config_path(
        run_manager=run_manager, reuse_dir=reuse_dir, run_config_file=run_config_file
    )

    run_config = load_or_init_run_config(
        run_config_path=run_config_path,
        run_manager=run_manager,
        pipeline_type=pipeline_type,
        pipeline_name=pipeline_name,
        get_params_func=get_processing_params,
        default_params=pipeline_config.extract_default_parameters(),
        working_dir=run_dir,
        parameters_name="parameters",
    )

    # ── Environment ─────────────────────────────────────────────────────────
    section("🌍 Environment")
    run_config, env_config = prepare_auth_and_env(run_config=run_config)
    kv("Host", env_config["host"])
    kv("Organization", env_config["organization_name"])

    # ── Normalize IO (resolve IDs/URLs) ─────────────────────────────────────
    section("📥 Inputs / 📤 Outputs")
    client = init_client(env_config=env_config)

    if pipeline_type == "DATASET_VERSION_CREATION":
        run_config["output"]["dataset_version"]["name"] = check_output_dataset_version(
            client=client,
            input_dataset_version_id=run_config["input"]["dataset_version"]["id"],
            output_name=run_config["output"]["dataset_version"]["name"],
            override_outputs=bool(run_config.get("override_outputs", False)),
        )

    enrich_run_config_with_metadata(client=client, run_config=run_config)
    saved_run_config_path = save_and_get_run_config_path(
        run_manager=run_manager, run_dir=run_dir, run_config=run_config
    )

    # ── Virtualenv / Python ─────────────────────────────────────────────────
    section("🐍 Virtual env")
    python_executable = prepare_python_executable(pipeline_config=pipeline_config)

    # ── Build command ────────────────────────────────────────────────────────
    section("▶️ Run")
    run_pipeline(
        pipeline_config=pipeline_config,
        run_config_path=saved_run_config_path,
        python_executable=python_executable,
        api_token=env_config["api_token"],
    )

    enrich_output_metadata_after_run(client=client, run_config=run_config)
    run_manager.save_run_config(run_dir=run_dir, config_data=run_config)

    typer.echo(
        typer.style(
            f"✅ Processing pipeline '{pipeline_name}' run complete: {run_dir.name}",
            fg=typer.colors.GREEN,
        )
    )
