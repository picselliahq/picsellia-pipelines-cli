import os
from typing import Optional, Dict, List, Any
from tinydb import TinyDB, Query


class SessionManager:
    """Handles global session and pipeline configurations using TinyDB."""

    DB_FILE: str = os.path.join(os.getcwd(), "session.json")

    def __init__(self) -> None:
        """Initialize the TinyDB database and define tables."""
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
        api_token: str = input("🔑 API Token: ")
        organization_id: str = input("🏢 Organization ID: ")

        self.global_table.truncate()  # Clear previous session data
        self.global_table.insert(
            {"api_token": api_token, "organization_id": organization_id}
        )

    def get_global_session(self) -> Optional[Dict[str, str]]:
        """Retrieve the global session details."""
        return self.global_table.all()[0] if self.global_table.all() else None

    # 🔹 PIPELINE MANAGEMENT 🔹 #

    def add_pipeline(self, name: str, data: Dict[str, Any]) -> None:
        """
        Add or update a pipeline configuration.

        Args:
            name (str): Name of the pipeline.
            data (dict): Pipeline configuration details.
        """
        Pipeline = Query()
        existing_pipeline = self.pipelines_table.search(Pipeline.name == name)

        if existing_pipeline:
            self.pipelines_table.update({"data": data}, Pipeline.name == name)
        else:
            self.pipelines_table.insert({"name": name, "data": data})

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
