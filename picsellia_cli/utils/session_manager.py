import getpass
import os
import shutil
from typing import Optional, Dict, List, Any
from tinydb import TinyDB, Query

import typer


class SessionManager:
    """Handles global session and pipeline configurations using TinyDB."""

    CONFIG_DIR: str = os.path.expanduser("~/.config/picsellia")
    DB_FILE: str = os.path.join(CONFIG_DIR, "session.json")

    def __init__(self) -> None:
        """Initialize the TinyDB database and define tables."""
        os.makedirs(self.CONFIG_DIR, exist_ok=True)

        self.db: TinyDB = TinyDB(self.DB_FILE)
        self.global_table: TinyDB = self.db.table("global")
        self.pipelines_table: TinyDB = self.db.table("pipelines")

    # 🔹 GLOBAL SESSION MANAGEMENT 🔹 #

    def ensure_session_initialized(self) -> None:
        """Ensure the global session is initialized; otherwise, prompt the user to set it up."""
        if not self.get_global_session():
            self.initialize_global_session()

    def initialize_global_session(self) -> None:
        """Prompt the user to enter API and organization details for the session."""
        print(
            "🌍 Global session is not initialized. Please provide the required details:"
        )
        api_token: str = getpass.getpass("🔑 API Token: ")
        organization_name: str = input("🏢 Organization Name: ")
        host = typer.prompt(
            "🌐 Enter the host (default: 'app.picsellia.com')",
            type=str,
            default="https://app.picsellia.com",
            show_default=True,
        )

        if host not in [
            "https://app.picsellia.com",
            "https://staging.picsellia.com",
            "http://localhost",
        ]:
            typer.echo(
                "❌ Invalid host. Setting the default host 'https://app.picsellia.com'."
            )
            host = "https://app.picsellia.com"

        self.global_table.truncate()  # Clear previous session data
        self.global_table.insert(
            {
                "api_token": api_token,
                "organization_name": organization_name,
                "host": host,
            }
        )

    def get_global_session(self) -> Optional[Dict[str, str]]:
        """Retrieve the global session details."""
        return self.global_table.all()[0] if self.global_table.all() else None

    # 🔹 PIPELINE MANAGEMENT 🔹 #

    def add_pipeline(self, name: str, data: Dict[str, Any]) -> bool:
        """
        Add or update a pipeline configuration.

        Args:
            name (str): Name of the pipeline.
            data (dict): Pipeline configuration details.
        """
        existing_pipeline = self.get_pipeline(name=name)

        if existing_pipeline:
            action = input(
                f"❌ Pipeline '{name}' already exists in the session. Do you want to (D)elete it, or (C)ancel? (d/c): "
            ).lower()
            if action == "d":
                self.remove_pipeline(name)
                old_pipeline_dir = existing_pipeline["pipeline_dir"]
                shutil.rmtree(old_pipeline_dir)
                print(f"✅ Pipeline '{name}' has been deleted.")
                self.add_pipeline(name, data)
                return True
            elif action == "c":
                print("Operation canceled. No changes made.")
                return False
            else:
                print("Invalid option, operation canceled.")
                return False
        else:
            self.pipelines_table.insert({"name": name, "data": data})
            return True

    def update_pipeline(self, name: str, data: Dict[str, Any]) -> None:
        """
        Update an existing pipeline configuration.

        Args:
            name (str): Name of the pipeline.
            data (dict): Updated pipeline configuration details.

        Returns:
            bool: True if pipeline was updated successfully, False otherwise.
        """
        Pipeline = Query()
        existing_pipeline = self.pipelines_table.search(Pipeline.name == name)

        if existing_pipeline:
            self.pipelines_table.update({"data": data}, Pipeline.name == name)
        else:
            raise (ValueError(f"Pipeline '{name}' not found."))

    def get_pipeline(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve pipeline configuration details.

        Args:
            name (str): Name of the pipeline.

        Returns:
            dict | None: The pipeline data if found, otherwise None.
        """
        Pipeline = Query()
        result = self.pipelines_table.search(Pipeline.name == name)
        return result[0]["data"] if result else None

    def list_pipelines(self) -> List[str]:
        """
        List all registered pipelines.

        Returns:
            list: A list of pipeline names.
        """
        return [pipeline["name"] for pipeline in self.pipelines_table.all()]

    def remove_pipeline(self, name: str) -> None:
        """
        Remove a pipeline configuration.

        Args:
            name (str): Name of the pipeline to remove.
        """
        Pipeline = Query()
        self.pipelines_table.remove(Pipeline.name == name)


# Initialize session manager
session_manager = SessionManager()
