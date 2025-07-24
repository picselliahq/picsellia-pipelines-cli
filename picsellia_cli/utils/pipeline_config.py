import importlib.util
import os
from pathlib import Path
from typing import Any

import toml


class PipelineConfig:
    def __init__(self, pipeline_name: str, search_path: Path = Path.cwd()):
        """Initialize the pipeline configuration by locating the directory and loading config/env."""
        self.pipeline_name = pipeline_name
        self.pipeline_dir = self.find_pipeline_dir(
            pipeline_name=pipeline_name, search_path=search_path
        )
        self.config_path = self.pipeline_dir / "config.toml"
        self.config = self.load_config()

    def load_config(self):
        if not self.config_path.exists():
            raise ValueError(f"Pipeline config not found at {self.config_path}")
        with self.config_path.open("r") as config_file:
            return toml.load(config_file)

    def get(self, section: str, key: str):
        return self.config.get(section, {}).get(key)

    def get_script_path(self, script_key: str) -> Path:
        """Get the full path to a script defined in the 'execution' section (e.g. 'local_pipeline_script')."""
        script_name = self.get("execution", script_key)
        if not script_name:
            raise ValueError(
                f"Script key '{script_key}' not found in 'execution' section."
            )
        return self.pipeline_dir / script_name

    def get_requirements_path(self) -> Path:
        return self.pipeline_dir / self.get("execution", "requirements_file")

    @staticmethod
    def find_pipeline_dir(pipeline_name: str, search_path: Path) -> Path:
        for root, dirs, files in os.walk(search_path):
            if Path(root).name == pipeline_name and "config.toml" in files:
                return Path(root)
        raise FileNotFoundError(
            f"❌ Pipeline '{pipeline_name}' directory or config.toml not found."
        )

    def save(self):
        with self.config_path.open("w") as f:
            toml.dump(self.config, f)

    def extract_default_parameters(self) -> dict[str, Any]:
        """
        Extract default parameters from the class defined in config.toml.

        Returns:
            dict[str, Any]: The default parameter dictionary.
        """
        class_path = self.get("execution", "parameters_class")
        if not class_path:
            raise ValueError("No parameters_class defined in config.toml")

        cls = self._import_class_from_path(class_path)
        try:
            instance = cls(log_data={})  # attempt instantiation with no input
        except Exception as e:
            raise ValueError(
                f"Failed to instantiate parameters class '{class_path}'. "
                f"Make sure all parameters have default values."
            ) from e
        return instance.to_dict()

    def _import_class_from_path(self, path_with_class: str):
        file_path, class_name = path_with_class.split(":")
        abs_path = self.pipeline_dir / file_path

        spec = importlib.util.spec_from_file_location("params_module", abs_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec from {abs_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        try:
            return getattr(module, class_name)
        except AttributeError:
            raise ImportError(f"Class '{class_name}' not found in '{file_path}'")
