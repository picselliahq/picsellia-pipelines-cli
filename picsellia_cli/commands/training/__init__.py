import typer

from .deployer import deploy_pipeline
from .initializer import init_training_pipeline
from .tester import test

app = typer.Typer(help="Manage training pipelines.")

app.command("init")(init_training_pipeline)
app.command("test")(test)
app.command("deploy")(deploy_pipeline)
