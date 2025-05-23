import os
from pathlib import Path

import toml
from dotenv import load_dotenv


class EnvConfig:
    def __init__(self, env_path=os.path.join(os.getcwd(), ".env")):
        load_dotenv(env_path)

    def get(self, key: str, default=None):
        return os.getenv(key, default)

    def require(self, key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Missing required env var: {key}")
        return value

    def get_api_token(self):
        return self.require("API_TOKEN")

    def get_organization_name(self):
        return self.require("ORGANIZATION_NAME")

    def get_host(self):
        return self.require("HOST")


class PipelineConfig:
    def __init__(self, pipeline_name: str, search_path: str = os.getcwd()):
        """Initialize the pipeline configuration by locating the directory and loading config/env."""
        self.pipeline_name = pipeline_name
        self.pipeline_dir = self.find_pipeline_dir(pipeline_name, search_path)
        self.config_path = self.pipeline_dir / "config.toml"
        self.config = self.load_config()
        self.env = EnvConfig()

    def load_config(self):
        if not self.config_path.exists():
            raise ValueError(f"Pipeline config not found at {self.config_path}")
        with open(self.config_path, "r") as config_file:
            return toml.load(config_file)

    def get(self, section: str, key: str):
        return self.config.get(section, {}).get(key)

    def get_parameters(self) -> dict:
        return self.config.get("default_parameters", {})

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
    def find_pipeline_dir(pipeline_name: str, search_path: str) -> Path:
        for root, dirs, files in os.walk(search_path):
            if Path(root).name == pipeline_name and "config.toml" in files:
                return Path(root)
        raise FileNotFoundError(
            f"❌ Pipeline '{pipeline_name}' directory or config.toml not found."
        )

    def save(self):
        with open(self.config_path, "w") as f:
            toml.dump(self.config, f)
