import toml
from pathlib import Path
from typing import Optional, Dict


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

    def get_latest_run_config(self) -> Optional[Dict]:
        latest = sorted(
            [p for p in self.runs_dir.glob("run*/run_config.toml")],
            key=lambda p: int(p.parent.name[3:]),
            reverse=True,
        )
        if latest:
            with open(latest[0], "r") as f:
                return toml.load(f)
        return None

    def save_run_config(self, run_dir: Path, config_data: Dict):
        with open(run_dir / "run_config.toml", "w") as f:
            toml.dump(config_data, f)

    def get_latest_run_dir(self) -> Optional[Path]:
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
