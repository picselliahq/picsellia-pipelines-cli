import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

import toml


class BaseTemplate(ABC):
    def __init__(
        self, pipeline_name: str, output_dir: str = ".", use_pyproject: bool = True
    ):
        self.pipeline_name = pipeline_name
        self.pipeline_dir = Path(output_dir) / pipeline_name
        abs_pipeline_path = self.pipeline_dir.resolve()
        cwd = Path.cwd().resolve()

        try:
            rel_path = abs_pipeline_path.relative_to(cwd)
        except ValueError:
            rel_path = abs_pipeline_path

        self.pipeline_module = rel_path.as_posix().replace("/", ".")
        self.utils_dir = self.pipeline_dir / "utils"
        self.use_pyproject = use_pyproject

    def write_all_files(self):
        self._write_file(self.pipeline_dir / "__init__.py", "")
        self._write_file(self.utils_dir / "__init__.py", "")

        for filename, content in self.get_main_files().items():
            self._write_file(self.pipeline_dir / filename, content)

        for filename, content in self.get_utils_files().items():
            self._write_file(self.utils_dir / filename, content)

        self.write_config_toml()

        self.write_run_config_toml()

    def _write_file(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    @abstractmethod
    def get_main_files(self) -> dict[str, str]:
        pass

    @abstractmethod
    def get_utils_files(self) -> dict[str, str]:
        pass

    @abstractmethod
    def get_config_toml(self) -> dict:
        """Return the pipeline-specific configuration that will be written to config.toml."""
        pass

    @abstractmethod
    def get_run_config_toml(self) -> str:
        """Return the default run_config.toml content, customized per pipeline type."""
        pass

    def write_run_config_toml(self):
        run_config_content = self.get_run_config_toml()
        run_config_path = self.pipeline_dir / "runs" / "run_config.toml"
        self._write_file(run_config_path, run_config_content)

    def write_config_toml(self):
        config_data = self.get_config_toml()
        config_path = self.pipeline_dir / "config.toml"
        with config_path.open("w") as config_file:
            toml.dump(config_data, config_file)

    def post_init_environment(self):
        """Create a local .venv and install dependencies from pyproject.toml or requirements.txt."""

        if shutil.which("uv") is None:
            raise RuntimeError(
                "❌ 'uv' is not installed or not in your PATH. Please install it from https://github.com/astral-sh/uv"
            )

        venv_path = self.pipeline_dir / ".venv"
        python_executable = (
            venv_path / "Scripts" / "python.exe"
            if os.name == "nt"
            else venv_path / "bin" / "python"
        )

        print(f"⚙️ Creating virtual environment in {venv_path} ...")
        subprocess.run(["uv", "venv"], cwd=str(self.pipeline_dir), check=True)

        if self.use_pyproject:
            print("🔒 Locking and syncing dependencies from pyproject.toml ...")
            subprocess.run(
                ["uv", "lock", "--project", str(self.pipeline_dir)], check=True
            )
            subprocess.run(
                ["uv", "sync", "--project", str(self.pipeline_dir)], check=True
            )
        else:
            req_path = self.pipeline_dir / "requirements.txt"
            print("📦 Installing from requirements.txt ...")
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python_executable),
                    "-r",
                    str(req_path),
                ],
                check=True,
            )

        print("\n✅ Virtual environment ready. Activate it with:\n")
        activate_cmd = (
            f"   {venv_path}\\Scripts\\activate.bat"
            if os.name == "nt"
            else f"   source {venv_path}/bin/activate"
        )
        print(activate_cmd)
