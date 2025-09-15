import typer

from picsellia_cli.commands.training.utils.test import (
    normalize_training_io,
    get_training_params,
    _print_training_io_summary,
)
from picsellia_cli.utils.env_utils import Environment
from picsellia_cli.utils.initializer import init_client
from picsellia_cli.utils.logging import hr, section, kv, step
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.run_manager import RunManager
from picsellia_cli.utils.tester import (
    select_run_dir,
    resolve_run_config_path,
    save_and_get_run_config_path,
    prepare_auth_and_env,
    load_or_init_run_config,
)


def launch_training(
    pipeline_name: str,
    run_config_file: str | None = None,
    reuse_dir: bool = False,
    organization: str | None = None,
    env: Environment | None = None,
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

    # ── Environment
    section("🌍 Environment")
    run_config, env_config = prepare_auth_and_env(
        run_config=run_config, organization=organization, env=env
    )

    kv("Host", env_config["host"])
    kv("Organization", env_config["organization_name"])

    # ── Normalize IO (resolve IDs, URLs, ensure bindings)
    section("📥 Inputs / 📤 Outputs")
    client = init_client(env_config=env_config)
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
        raise typer.Exit()

    try:
        experiment.launch()
    except Exception as e:
        typer.echo(f"❌ Launch failed: {e}")
        raise typer.Exit()

    org_id = getattr(getattr(client, "connexion", None), "organization_id", None)
    host_base = getattr(getattr(client, "connexion", None), "host", "").rstrip("/")

    kv("Status", "Launched ✅")
    url = f"{host_base}/{org_id}/jobs"
    kv("Job URL", url, color=typer.colors.BLUE)

    hr()
