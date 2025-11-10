import typer
from picsellia.exceptions import ResourceNotFoundError

from picsellia_pipelines_cli.commands.training.utils.test import (
    _print_training_io_summary,
    get_training_params,
    normalize_training_io,
)
from picsellia_pipelines_cli.utils.initializer import init_client
from picsellia_pipelines_cli.utils.logging import hr, kv, section, step
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig
from picsellia_pipelines_cli.utils.run_manager import RunManager
from picsellia_pipelines_cli.utils.tester import (
    load_or_init_run_config,
    prepare_auth_and_env,
    resolve_run_config_path,
    save_and_get_run_config_path,
    select_run_dir,
)


def launch_training(
    pipeline_name: str, run_config_file: str | None = None, reuse_dir: bool = False
):
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)
    pipeline_type = pipeline_config.get("metadata", "type")
    run_manager = RunManager(pipeline_dir=pipeline_config.pipeline_dir)

    # ── Run directory ────────────────────────────────────────────────────────
    run_dir = select_run_dir(run_manager=run_manager, reuse_dir=reuse_dir)
    run_config_path = resolve_run_config_path(
        run_manager=run_manager, reuse_dir=reuse_dir, run_config_file=run_config_file
    )

    run_config = load_or_init_run_config(
        run_config_path=run_config_path,
        run_manager=run_manager,
        pipeline_type=pipeline_type,
        pipeline_name=pipeline_name,
        get_params_func=get_training_params,
        default_params=pipeline_config.extract_default_parameters(),
        working_dir=run_dir,
        parameters_name="hyperparameters",
    )

    # ── Environment ─────────────────────────────────────────────────────────
    section("🌍 Environment")
    run_config, env_config = prepare_auth_and_env(run_config=run_config)
    kv("Host", env_config["host"])
    kv("Organization", env_config["organization_name"])

    # ── Normalize IO (resolve IDs, URLs, ensure bindings)
    section("📥 Inputs / 📤 Outputs")
    client = init_client(env_config=env_config)

    _apply_override_for_experiment(client=client, run_config=run_config)

    try:
        normalize_training_io(client=client, run_config=run_config)
    except typer.Exit as e:
        kv("❌ IO normalization failed", str(e))
        raise

    _print_training_io_summary(run_config)

    # ── Persist run config to run dir ────────────────────────────────────────
    _ = save_and_get_run_config_path(
        run_manager=run_manager, run_dir=run_dir, run_config=run_config
    )

    # ── Launch
    section("🟩 Launch")

    # Experiment target (from normalized config)
    exp = (run_config.get("output") or {}).get("experiment") or {}
    exp_id = exp.get("id")
    if not exp_id:
        typer.echo("❌ Missing output.experiment.id after normalization.")
        raise typer.Exit()

    kv("Experiment ID", exp_id)
    if exp.get("name"):
        kv("Experiment", exp["name"])
    if exp.get("url"):
        kv("Experiment URL", exp["url"])

    step(1, "Submitting training job…")
    try:
        experiment = client.get_experiment_by_id(exp_id)
    except Exception as e:
        typer.echo(f"❌ Could not fetch experiment '{exp_id}': {e}")
        raise typer.Exit() from e

    try:
        experiment.launch()
    except Exception as e:
        typer.echo(f"❌ Launch failed: {e}")
        raise typer.Exit() from e

    org_id = getattr(getattr(client, "connexion", None), "organization_id", None)
    host_base = getattr(getattr(client, "connexion", None), "host", "").rstrip("/")

    kv("Status", "Launched ✅")
    url = f"{host_base}/{org_id}/jobs"
    kv("Job URL", url, color=typer.colors.BLUE)

    hr()


def _apply_override_for_experiment(client, run_config: dict) -> None:
    if not bool(run_config.get("override_outputs", False)):
        return

    exp = (run_config.get("output") or {}).get("experiment") or {}
    exp_id = exp.get("id")
    exp_name = exp.get("name")
    project_name = exp.get("project_name")

    if exp_id or not (exp_name and project_name):
        return

    try:
        project = client.get_project(project_name=project_name)
        try:
            existing = project.get_experiment(name=exp_name)
        except ResourceNotFoundError:
            existing = None

        if existing is not None:
            existing.delete()
            typer.echo(
                typer.style(
                    f"🧹 Deleted existing experiment '{exp_name}' in project '{project_name}' (override enabled).",
                    fg=typer.colors.YELLOW,
                )
            )
    except Exception as e:
        typer.echo(
            typer.style(
                f"⚠️ Override skipped for experiment '{exp_name}' in '{project_name}': {e}",
                fg=typer.colors.YELLOW,
            )
        )
