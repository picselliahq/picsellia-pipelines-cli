"""Dataset version constraints of a training model version.

A model version can declare which dataset versions a training expects, as
named groups of aliases (e.g. ``train`` / ``val`` / ``test``). The platform
uses them to assign dataset versions to the experiment.

They are declared in ``config.toml``::

    [dataset_constraints]
    required = true

    [[dataset_constraints.groups]]
    name = "1 dataset"
    description = "One dataset version, split at random into train / val / test."
    aliases = ["train"]

    [[dataset_constraints.groups]]
    name = "3 datasets"
    aliases = ["train", "val", "test"]
    alias_descriptions = { train = "Training images" }

The SDK does not expose this field yet, so it is sent with a raw PATCH on the
model version, the same way ``ModelVersion.update`` does.
"""

import json
from typing import Any

import typer

CONFIG_SECTION = "dataset_constraints"


def _fail(message: str) -> None:
    typer.echo(f"❌ Invalid [{CONFIG_SECTION}] in config.toml: {message}")
    raise typer.Exit(code=1)


def _parse_alias_descriptions(
    raw: dict, aliases: list[str], where: str
) -> dict[str, str]:
    alias_descriptions = raw.get("alias_descriptions", {})
    if not isinstance(alias_descriptions, dict):
        _fail(f'{where}.alias_descriptions must be a table, e.g. {{ train = "..." }}.')
    unknown_aliases = sorted(set(alias_descriptions) - set(aliases))
    if unknown_aliases:
        _fail(
            f"{where}.alias_descriptions describes aliases not in 'aliases': "
            f"{', '.join(unknown_aliases)}."
        )
    if not all(isinstance(d, str) for d in alias_descriptions.values()):
        _fail(f"{where}.alias_descriptions values must be strings.")
    return alias_descriptions


def _parse_group(raw: Any, index: int) -> dict[str, Any]:
    where = f"groups[{index}]"
    if not isinstance(raw, dict):
        _fail(f"{where} must be a table (use [[{CONFIG_SECTION}.groups]]).")

    unknown = set(raw) - {"name", "description", "aliases", "alias_descriptions"}
    if unknown:
        _fail(f"{where} has unknown keys: {', '.join(sorted(unknown))}.")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        _fail(f"{where} must have a non-empty 'name'.")
    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        _fail(f"{where}.description must be a string.")

    raw_aliases = raw.get("aliases")
    if not isinstance(raw_aliases, list) or not raw_aliases:
        _fail(f"{where} ('{name}') must declare at least one alias in 'aliases'.")

    if not all(isinstance(a, str) and a.strip() for a in raw_aliases):
        _fail(f"{where} ('{name}'): 'aliases' must be a list of non-empty strings.")
    aliases = [a.strip() for a in raw_aliases]
    duplicates = sorted({a for a in aliases if aliases.count(a) > 1})
    if duplicates:
        _fail(f"{where} ('{name}') repeats aliases: {', '.join(duplicates)}.")

    alias_descriptions = _parse_alias_descriptions(raw, aliases, where)

    constraints = [
        {"alias": a, "description": alias_descriptions.get(a) or None} for a in aliases
    ]

    return {
        "name": name.strip(),
        "description": description or None,
        "constraints": constraints,
    }


def parse_dataset_constraints(config: dict) -> dict[str, Any] | None:
    """Read and validate ``[dataset_constraints]`` from a loaded config.toml.

    Returns:
        The API payload (``{"required": bool, "constraints_groups": [...]}``),
        or None when the section is absent, meaning the CLI leaves the
        constraints already set on the platform untouched.

    Raises:
        typer.Exit: If the section is malformed.
    """
    section = config.get(CONFIG_SECTION)
    if section is None:
        return None
    if not isinstance(section, dict):
        _fail("it must be a table.")

    unknown = set(section) - {"required", "groups"}
    if unknown:
        _fail(f"unknown keys: {', '.join(sorted(unknown))}.")

    required = section.get("required", False)
    if not isinstance(required, bool):
        _fail("'required' must be true or false.")

    raw_groups = section.get("groups", [])
    if not isinstance(raw_groups, list):
        _fail(f"'groups' must be an array of tables ([[{CONFIG_SECTION}.groups]]).")

    groups = [_parse_group(g, i) for i, g in enumerate(raw_groups)]
    names = [g["name"] for g in groups]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        _fail(f"group names must be unique: {', '.join(duplicates)}.")
    if required and not groups:
        _fail("'required = true' needs at least one group.")

    return {"required": required, "constraints_groups": groups}


def describe_dataset_constraints(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (label, value) rows to display the constraints in the CLI."""
    rows = [("Required", "yes" if payload["required"] else "no")]
    if not payload["constraints_groups"]:
        rows.append(("Groups", "none (constraints cleared)"))
    for group in payload["constraints_groups"]:
        aliases = ", ".join(c["alias"] for c in group["constraints"])
        rows.append((group["name"], aliases))
    return rows


def apply_dataset_constraints(model_version, payload: dict[str, Any]) -> None:
    """Replace the dataset version constraints of a model version."""
    model_version.connection.patch(
        f"/api/model/version/{model_version.id}",
        data=json.dumps({"dataset_version_constraints": payload}),
    )
