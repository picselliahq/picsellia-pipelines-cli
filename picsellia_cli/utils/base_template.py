import os
import subprocess
from abc import ABC, abstractmethod

import toml


class BaseTemplate(ABC):
    BASE_DIR = "pipelines"

    def __init__(
        self, pipeline_name: str, output_dir: str = ".", use_pyproject: bool = True
    ):
        self.pipeline_name = pipeline_name
        self.pipeline_dir = os.path.join(output_dir, pipeline_name)
        self.pipeline_module = self.pipeline_dir.replace("/", ".")
        self.utils_dir = os.path.join(self.pipeline_dir, "utils")
        self.use_pyproject = use_pyproject

    def write_all_files(self):
        self._write_file(os.path.join(self.BASE_DIR, "__init__.py"), "")
        self._write_file(os.path.join(self.pipeline_dir, "__init__.py"), "")
        self._write_file(os.path.join(self.utils_dir, "__init__.py"), "")

        for filename, content in self.get_main_files().items():
            self._write_file(os.path.join(self.pipeline_dir, filename), content)

        for filename, content in self.get_utils_files().items():
            self._write_file(os.path.join(self.utils_dir, filename), content)

        self.write_config_toml()

    def _write_file(self, filepath: str, content: str):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(content)

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

    def write_config_toml(self):
        """Write the config.toml file with pipeline-specific settings."""
        config_data = self.get_config_toml()

        # Write config.toml to the pipeline directory
        config_path = os.path.join(self.pipeline_dir, "config.toml")
        with open(config_path, "w") as config_file:
            toml.dump(config_data, config_file)

    import subprocess

    def post_init_environment(self):
        """Create a local .venv and install dependencies from pyproject.toml or requirements.txt."""
        pipeline_path = self.pipeline_dir
        python_executable = (
            os.path.join(pipeline_path, ".venv", "bin", "python3")
            if os.name != "nt"
            else os.path.join(pipeline_path, ".venv", "Scripts", "python.exe")
        )

        print(f"⚙️ Creating virtual environment in {pipeline_path}/.venv ...")
        subprocess.run(["uv", "venv"], cwd=pipeline_path, check=True)

        if self.use_pyproject:
            print("🔒 Locking and syncing dependencies from pyproject.toml ...")
            subprocess.run(["uv", "lock", "--project", pipeline_path], check=True)
            subprocess.run(["uv", "sync", "--project", pipeline_path], check=True)
        else:
            req_path = os.path.join(pipeline_path, "requirements.txt")
            print("📦 Installing from requirements.txt ...")
            subprocess.run(
                ["uv", "pip", "install", "--python", python_executable, "-r", req_path],
                check=True,
            )

        print("\n✅ Virtual environment ready. Activate it with:\n")
        print(
            f"   source {pipeline_path}/.venv/bin/activate"
            if os.name != "nt"
            else f"   {pipeline_path}\\.venv\\Scripts\\activate.bat"
        )
