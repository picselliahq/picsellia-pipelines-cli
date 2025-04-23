import typer

from .initializer import init_processing_pipeline
from .manager import remove_pipeline, list_pipelines
from .tester import test_pipeline
from .deployer import deploy_pipeline

app = typer.Typer(help="Manage dataset processing pipelines.")

app.command("init")(init_processing_pipeline)
app.command("remove")(remove_pipeline)
app.command("list")(list_pipelines)
app.command("test")(test_pipeline)
app.command("deploy")(deploy_pipeline)
