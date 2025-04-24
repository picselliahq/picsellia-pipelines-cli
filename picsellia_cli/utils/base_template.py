from abc import ABC, abstractmethod
import os


class BaseTemplate(ABC):
    BASE_DIR = "pipelines"
    
    
    def __init__(self, pipeline_name: str):
        self.pipeline_name = pipeline_name
        self.pipeline_dir = os.path.join(self.BASE_DIR, pipeline_name)
        self.utils_dir = os.path.join(self.pipeline_dir, "utils")

    def write_all_files(self):
        self._write_file(os.path.join(self.BASE_DIR, "__init__.py"), "")
        self._write_file(os.path.join(self.pipeline_dir, "__init__.py"), "")
        self._write_file(os.path.join(self.utils_dir, "__init__.py"), "")

        for filename, content in self.get_main_files().items():
            self._write_file(os.path.join(self.pipeline_dir, filename), content)

        for filename, content in self.get_utils_files().items():
            self._write_file(os.path.join(self.utils_dir, filename), content)

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