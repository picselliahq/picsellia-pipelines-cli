from typer import Typer
from picsellia_cli.commands.processing import app as processing_app
from picsellia_cli.commands.training import app as training_app

app = Typer()

app.add_typer(processing_app, name="processing")
app.add_typer(training_app, name="training")

if __name__ == "__main__":
    app()
