import os
from abc import ABC, abstractmethod

import toml


class BaseTemplate(ABC):
    BASE_DIR = "pipelines"

    def __init__(self, pipeline_name: str):
        self.pipeline_name = pipeline_name
        self.pipeline_dir = os.path.join(self.BASE_DIR, pipeline_name)
        self.pipeline_module = self.pipeline_dir.replace("/", ".")
        self.utils_dir = os.path.join(self.pipeline_dir, "utils")

    def write_all_files(self):
        self._write_file(os.path.join(self.BASE_DIR, "__init__.py"), "")
        self._write_file(os.path.join(self.pipeline_dir, "__init__.py"), "")
        self._write_file(os.path.join(self.utils_dir, "__init__.py"), "")
        self._write_file(os.path.join(self.utils_dir, "config.py"), CONFIG_UTILS)

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


CONFIG_UTILS = """import os
import toml
from typing import Dict


def load_processing_parameters() -> Dict:
    \"\"\"
    Load processing_parameters from config.toml in the current pipeline directory.
    Assumes this file is located in utils/ under the pipeline root.
    \"\"\"
    current_dir = os.path.dirname(os.path.dirname(__file__))
    config_path = os.path.join(current_dir, "config.toml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"config.toml not found in {config_path}")

    with open(config_path, "r") as f:
        config = toml.load(f)
    return config.get("processing_parameters", {})
"""
