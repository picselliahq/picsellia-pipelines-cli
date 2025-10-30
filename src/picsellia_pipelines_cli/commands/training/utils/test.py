import json
from pathlib import Path

import toml
import typer
from picsellia import Client, Experiment, Project
from picsellia.exceptions import ResourceConflictError, ResourceNotFoundError

from picsellia_pipelines_cli.utils.logging import kv
from picsellia_pipelines_cli.utils.run_manager import RunManager

REQUIRED_TRAIN_INPUT_KEYS = ("train_dataset", "model_version")


def print_config_io_summary_for_training(config: dict):
    summary = {
        "experiment_id": config.get("experiment_id"),
        "parameters": config.get("parameters", {}),
        "auth": {
            "host": config.get("auth", {}).get("host"),
            "organization_name": config.get("auth", {}).get("organization_name"),
        },
        "run": {"working_dir": config.get("run", {}).get("working_dir")},
    }
    typer.echo(
        typer.style("🧾 Reusing previous training config:\n", fg=typer.colors.CYAN)
    )
    typer.echo(json.dumps(summary, indent=2))


def prompt_training_params(stored_params: dict) -> dict:
    experiment_id = typer.prompt(
        typer.style("🧪 Experiment ID", fg=typer.colors.CYAN),
        default=stored_params.get("experiment_id", ""),
    )
    return {"experiment_id": experiment_id}


def get_training_params(
    run_manager: RunManager | None,
    pipeline_type: str,
    pipeline_name: str,
    config_file: Path | None = None,
) -> dict:
    if config_file is not None and config_file.exists():
        with config_file.open("r") as f:
            return toml.load(f)

    latest_config = None

    if run_manager is not None:
        latest_config_path = run_manager.get_latest_run_config_path()
        if latest_config_path:
            p = Path(latest_config_path)
            if p.exists():
                with p.open("r") as f:
                    latest_config = toml.load(f)

    stored_params: dict = latest_config or {}

    if latest_config:
        print_config_io_summary_for_training(latest_config)
        reuse = typer.confirm(
            typer.style("📝 Do you want to reuse this config?", fg=typer.colors.CYAN),
            default=True,
        )
        if reuse:
            return latest_config

    params = prompt_training_params(stored_params)
    return params


def normalize_training_io(client: Client, run_config: dict) -> None:
    experiment = run_config.get("output", {}).get("experiment", {})

    experiment_id = experiment.get("id")
    experiment_name = experiment.get("name")
    project_name = experiment.get("project_name")
    override = bool(run_config.get("override_outputs", False))

    if experiment_id:
        _handle_experiment_by_id(
            client=client, run_config=run_config, experiment_id=experiment_id
        )
    elif experiment_name and project_name:
        _handle_experiment_by_name(
            client=client,
            run_config=run_config,
            experiment_name=experiment_name,
            project_name=project_name,
            override_outputs=override,
        )
    else:
        _raise_invalid_config()


def _handle_experiment_by_id(client: Client, run_config: dict, experiment_id: str):
    experiment = client.get_experiment_by_id(id=experiment_id)
    _resolve_input_metadata(client=client, run_config=run_config)

    if not _has_required_inputs(run_config=run_config):
        _exit_missing_inputs()

    _ensure_experiment_has_datasets(
        client=client, experiment=experiment, run_config=run_config
    )

    _ensure_experiment_has_model_version(
        client=client, experiment=experiment, run_config=run_config
    )

    _set_experiment_metadata(experiment=experiment, run_config=run_config)


def _handle_experiment_by_name(
    client: Client,
    run_config: dict,
    experiment_name: str,
    project_name: str,
    override_outputs: bool = False,
):
    if not _has_required_inputs(run_config=run_config):
        _exit_case_b_inputs()

    project = _get_or_create_project(client=client, project_name=project_name)
    experiment = _get_or_create_experiment_in_project(
        project=project,
        experiment_name=experiment_name,
        override_outputs=override_outputs,
    )

    _set_experiment_metadata(experiment=experiment, run_config=run_config)
    _resolve_input_metadata(client=client, run_config=run_config)

    if not _has_required_inputs(run_config=run_config):
        _exit_missing_inputs()

    _ensure_project_has_datasets(client=client, project=project, run_config=run_config)
    _ensure_experiment_has_datasets(
        client=client, experiment=experiment, run_config=run_config
    )
    _ensure_experiment_has_model_version(
        client=client, experiment=experiment, run_config=run_config
    )


_DATASET_KEYS = (
    "train_dataset_version",
    "test_dataset_version",
    "validation_dataset_version",
)
_ALIAS_MAP = {
    "train_dataset_version": "train",
    "test_dataset_version": "test",
    "validation_dataset_version": "val",
}


def _ensure_project_has_datasets(
    client: Client, project: Project, run_config: dict
) -> None:
    """Ajoute chaque dataset version d'input au projet (si possible)."""
    inp = (run_config or {}).get("input") or {}
    for key in _DATASET_KEYS:
        ref = inp.get(key) or {}
        dsv_id = _ensure_dataset_version_id(client, ref)
        if not dsv_id:
            continue

        try:
            dsv = client.get_dataset_version_by_id(dsv_id)
        except Exception as e:
            typer.echo(
                f"⚠️ Could not fetch dataset version {dsv_id} for project attach: {e}"
            )
            continue

        try:
            project.attach_dataset(dataset_version=dsv)
        except ResourceConflictError:
            continue


def _ensure_experiment_has_datasets(
    client: Client, experiment: Experiment, run_config: dict
) -> None:
    """Attache datasets à l'expériment avec alias (train/test/val)."""
    inp = (run_config or {}).get("input") or {}

    for key in _DATASET_KEYS:
        alias = _ALIAS_MAP[key]
        ref = inp.get(key) or {}
        dsv_id = _ensure_dataset_version_id(client, ref)
        if not dsv_id:
            continue

        try:
            dataset_version = client.get_dataset_version_by_id(dsv_id)
        except Exception as e:
            typer.echo(
                f"⚠️ Could not fetch dataset version {dsv_id} for project attach: {e}"
            )
            continue

        try:
            experiment.attach_dataset(name=alias, dataset_version=dataset_version)
        except ResourceConflictError:
            continue


def _ensure_experiment_has_model_version(
    client: Client, experiment: Experiment, run_config: dict
) -> None:
    inp = (run_config or {}).get("input") or {}
    mv = (inp.get("model_version") or {}).copy()

    # --- normalize visibility
    visibility = mv.get("visibility")
    if visibility is None and isinstance(mv.get("public"), bool):
        visibility = "public" if mv["public"] else "private"
    if visibility not in ("public", "private"):
        visibility = "private"

    # --- choose handler
    if visibility == "public":
        _attach_public_model_version(client, experiment, run_config, mv, inp)
    else:
        _attach_private_model_version(client, experiment, run_config, mv, inp)


def _attach_public_model_version(client, experiment, run_config, mv, inp):
    origin_name = mv.get("origin_name")
    version_name = mv.get("name") or mv.get("version_name")
    if not (origin_name and version_name):
        typer.echo(
            "❌ Public model requires 'input.model_version.origin_name' "
            "and 'input.model_version.name' (or 'version_name')."
        )
        raise typer.Exit()

    try:
        pub_model = client.get_public_model(name=origin_name)
        pub_mv = pub_model.get_version(version=version_name)
    except Exception as e:
        typer.echo(f"❌ Unable to resolve public model/version: {e}")
        raise typer.Exit() from None

    _enrich_and_attach(experiment, run_config, inp, mv, pub_mv, "public", origin_name)


def _attach_private_model_version(client, experiment, run_config, mv, inp):
    mv_obj = None
    mv_id = mv.get("id")
    if mv_id:
        try:
            mv_obj = client.get_model_version_by_id(mv_id)
        except Exception as e:
            typer.echo(f"❌ Could not fetch private model version by id '{mv_id}': {e}")
            raise typer.Exit() from None
    else:
        origin_name = mv.get("origin_name")
        version_name = mv.get("name") or mv.get("version_name")
        if not (origin_name and version_name):
            typer.echo(
                "❌ Private model requires 'input.model_version.id' "
                "or ('origin_name' + 'name'/'version_name')."
            )
            raise typer.Exit()
        try:
            model = client.get_model(name=origin_name)
            mv_obj = model.get_version(version=version_name)
        except Exception as e:
            typer.echo(f"❌ Unable to resolve private model/version: {e}")
            raise typer.Exit() from None

    _enrich_and_attach(experiment, run_config, inp, mv, mv_obj, "private")


def _enrich_and_attach(experiment, run_config, inp, mv, mv_obj, vis, origin_name=None):
    mv.update(
        {
            "id": str(mv_obj.id),
            "name": mv_obj.name,
            "origin_name": origin_name or getattr(mv_obj, "origin_name", None),
            "url": mv_obj.get_resource_url_on_platform(),
            "visibility": vis,
        }
    )
    inp["model_version"] = mv
    run_config["input"] = inp
    try:
        experiment.attach_model_version(model_version=mv_obj)
    except ResourceConflictError:
        pass


def _ensure_dataset_version_id(client: Client, ref: dict) -> str | None:
    """Retourne/refill l'id de dataset version depuis ref (id ou origin_name+name/version_name)."""
    if not isinstance(ref, dict):
        return None
    if ref.get("id"):
        return str(ref["id"])

    origin_name = ref.get("origin_name")
    name = ref.get("name") or ref.get("version_name")
    if not (origin_name and name):
        return None

    try:
        ds = client.get_dataset(name=origin_name)
        dsv = ds.get_version(version_name=name)
        # enrichissement minimal si utile
        ref.update(
            {
                "id": str(dsv.id),
                "name": dsv.version,
                "origin_name": ds.name,
                "version_name": dsv.version,
                "url": dsv.get_resource_url_on_platform(),
            }
        )
        return str(dsv.id)
    except Exception:
        return None


def _resolve_model_version_id_from_names(client: Client, mv_ref: dict) -> str | None:
    """Déduit l'id de model version si on n'a que origin_name + (name|version_name), public/private."""
    if not isinstance(mv_ref, dict):
        return None
    origin_name = mv_ref.get("origin_name")
    name = mv_ref.get("name") or mv_ref.get("version_name")
    if not (origin_name and name):
        return None

    visibility = mv_ref.get("visibility")
    if visibility is None and isinstance(mv_ref.get("public"), bool):
        visibility = "public" if mv_ref["public"] else "private"
    if visibility not in ("public", "private"):
        visibility = "private"

    try:
        if visibility == "public":
            pub_model = client.get_public_model(name=origin_name)
            pub_mv = pub_model.get_version(version_name=name)
            return str(pub_mv.id)
        else:
            model = client.get_model(name=origin_name)
            mv = model.get_version(version_name=name)
            return str(mv.id)
    except Exception:
        return None


def _maybe_clear_experiment_model_version(experiment: Experiment) -> None:
    _try_call(experiment, ["remove_model_version", "detach_model_version"])
    _try_call(experiment, ["clear_model_version"])


def _try_call(obj, method_names: list[str], *args, **kwargs) -> bool:
    """Tente d’appeler la première méthode existante parmi method_names."""
    for name in method_names:
        fn = getattr(obj, name, None)
        if callable(fn):
            try:
                fn(*args, **kwargs)
                return True
            except TypeError:
                # Retente sans *args si la signature ne correspond pas
                try:
                    fn(**kwargs)
                    return True
                except Exception:
                    continue
            except Exception:
                continue
    return False


def _has_id_or_name_origin(
    d: dict | None, *, accept_version_name: bool = False
) -> bool:
    if not isinstance(d, dict):
        return False
    if d.get("id"):
        return True
    name = d.get("name")
    if accept_version_name and not name:
        name = d.get("version_name")
    return bool(name and d.get("origin_name"))


def _has_required_inputs(run_config: dict) -> bool:
    inp = (run_config or {}).get("input") or {}

    train_ref = inp.get("train_dataset_version") or inp.get("train_dataset")
    model_ref = inp.get("model_version")

    train_ok = _has_id_or_name_origin(
        train_ref, accept_version_name=True
    )  # dataset version: name ou version_name + origin_name
    model_ok = _has_id_or_name_origin(
        model_ref, accept_version_name=True
    )  # model version: name (ou version_name) + origin_name

    return train_ok and model_ok


def _exit_missing_inputs():
    typer.echo(
        "❌ Missing required training inputs: train_dataset_version and/or model_version."
    )
    raise typer.Exit()


def _exit_case_b_inputs():
    typer.echo(
        "❌ For case B, provide train_dataset_version + model_version + experiment name & project name."
    )
    raise typer.Exit()


def _raise_invalid_config():
    typer.echo(
        "❌ Invalid training config. Provide either experiment.id or experiment.name with required inputs."
    )
    raise typer.Exit()


def _set_experiment_metadata(experiment: Experiment, run_config: dict):
    run_config.setdefault("output", {}).setdefault("experiment", {}).update(
        {
            "id": str(experiment.id),
            "name": experiment.name,
            "url": experiment.get_resource_url_on_platform(),
        }
    )


def _resolve_input_metadata(client: Client, run_config: dict):
    input = run_config.get("input", {})
    _resolve_dataset_metadata(client, input)
    _resolve_model_metadata(client, input)
    run_config["input"] = input


def _resolve_dataset_metadata(client, input: dict):
    def resolve_dsv(key):
        slot = input.get(key, {})
        dsv_id = slot.get("id")
        if not dsv_id:
            return
        try:
            dsv = client.get_dataset_version_by_id(dsv_id)
            input[key] = {
                "id": dsv_id,
                "name": dsv.version,
                "origin_name": dsv.name,
                "version_name": dsv.version,
                "url": dsv.get_resource_url_on_platform(),
            }
        except Exception as e:
            typer.echo(f"⚠️ Could not resolve dataset metadata for {key}: {e}")

    for k in (
        "train_dataset_version",
        "test_dataset_version",
        "validation_dataset_version",
    ):
        resolve_dsv(k)


def _resolve_model_metadata(client, input: dict):
    mv = input.get("model_version", {})
    visibility = mv.get("visibility")
    if visibility is None and isinstance(mv.get("public"), bool):
        visibility = "public" if mv["public"] else "private"
    if visibility not in ("public", "private"):
        visibility = "private"

    mv_id = mv.get("id")
    mv_version_name = mv.get("name") or mv.get("version_name")
    mv_origin_name = mv.get("origin_name")

    try:
        if visibility == "public":
            if not (mv_origin_name and mv_version_name):
                raise ValueError(
                    "Public model requires 'input.model_version.origin_name' "
                    "and version 'input.model_version.name' (or 'version_name')."
                )
            pub_model = client.get_public_model(name=mv_origin_name)
            pub_mv = pub_model.get_version(version=mv_version_name)
            input["model_version"] = {
                "id": str(pub_mv.id),
                "name": pub_mv.name,
                "origin_name": mv_origin_name,
                "url": pub_mv.get_resource_url_on_platform(),
                "visibility": "public",
            }
        else:
            model_version = (
                client.get_model_version_by_id(mv_id)
                if mv_id
                else client.get_model(name=mv_origin_name).get_version(
                    version=mv_version_name
                )
            )
            input["model_version"] = {
                "id": str(model_version.id),
                "name": model_version.name,
                "origin_name": model_version.origin_name,
                "url": model_version.get_resource_url_on_platform(),
                "visibility": "private",
            }

    except Exception as e:
        typer.echo(f"❌ Could not resolve model metadata: {e}")
        raise typer.Exit() from None


def _get_or_create_project(client: Client, project_name: str):
    try:
        project = client.get_project(project_name=project_name)
    except ResourceNotFoundError:
        project = client.create_project(name=project_name)
    return project


def _get_or_create_experiment_in_project(
    project: Project,
    experiment_name: str,
    override_outputs: bool = False,
) -> Experiment:
    try:
        existing = project.get_experiment(name=experiment_name)
    except ResourceNotFoundError:
        return project.create_experiment(name=experiment_name)

    if not override_outputs:
        return existing
    else:
        existing.delete()
        return project.create_experiment(name=experiment_name)


def _print_training_io_summary(run_config: dict) -> None:
    out = run_config.get("output", {}) or {}
    exp = out.get("experiment", {}) or {}
    if exp:
        if exp.get("url"):
            kv("Experiment URL", exp["url"])

    inp = run_config.get("input", {}) or {}

    mv = inp.get("model_version") or {}
    if mv:
        if mv.get("url"):
            kv("Model URL", mv["url"])
