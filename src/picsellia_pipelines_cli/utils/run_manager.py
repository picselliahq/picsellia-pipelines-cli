from pathlib import Path

import toml


class RunManager:
    def __init__(self, pipeline_dir: Path):
        self.runs_dir = pipeline_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def get_next_run_dir(self) -> Path:
        existing = sorted(
            [
                int(p.name[3:])
                for p in self.runs_dir.glob("run*")
                if p.name[3:].isdigit()
            ],
            reverse=True,
        )
        next_index = (existing[0] + 1) if existing else 1
        run_dir = self.runs_dir / f"run{next_index}"
        run_dir.mkdir()
        return run_dir

    def get_latest_run_config_path(self) -> Path | None:
        candidates = sorted(
            self.runs_dir.glob("run*/run_config.toml"),
            key=lambda p: int(p.parent.name[3:]),
            reverse=True,
        )
        return candidates[0] if candidates else None

    def save_run_config(self, run_dir: Path, config_data: dict):
        config_path = run_dir / "run_config.toml"
        with config_path.open("w") as f:
            toml.dump(config_data, f)

    def get_latest_run_dir(self) -> Path | None:
        runs = sorted(
            [
                p
                for p in self.runs_dir.glob("run*")
                if p.is_dir() and p.name[3:].isdigit()
            ],
            key=lambda p: int(p.name[3:]),
            reverse=True,
        )
        return runs[0] if runs else None
