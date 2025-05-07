# 🧪 Picsellia Pipelines CLI

A command-line tool to create, test, deploy, and manage training and processing pipelines for [Picsellia](https://picsellia.com/).

Built with [Typer](https://typer.tiangolo.com/) for intuitive CLI usage.

---

## Installation

Clone the repository and install dependencies with Poetry:

```bash
poetry install
```
This will automatically install the CLI and register the pipeline-cli command.

If you're using `poetry shell`, you can now run:
```bash
pipeline-cli --help
```

Or from outside the shell:
```bash
poetry run pipeline-cli --help
```

## Available Commands
🔹 CLI structure

```bash
pipeline-cli [training|processing] [init|test|deploy|remove|list|smoke-test]
```

Each subcommand is documented below.


## Processing Pipelines
Commands for managing dataset processing pipelines.

🔹 Initialize a processing pipeline

```bash
pipeline-cli processing init <pipeline_name> --template simple
```

Scaffolds a pipeline with a processing script and template configuration.

🔹 Run local test

```bash
pipeline-cli processing test <pipeline_name>
```

Runs the pipeline locally with input and output dataset version IDs.

🔹 Deploy to Picsellia

```bash
pipeline-cli processing deploy <pipeline_name> --cpu 4 --gpu 0
```

Builds and pushes the Docker image, then registers the processing job in Picsellia.

## Training Pipelines

Commands for managing model training pipelines.

🔹 Initialize a training pipeline

```bash
pipeline-cli training init <pipeline_name> --template [simple|ultralytics]
```

Creates the directory structure and registers a model version in Picsellia.

🔹 Run local test

```bash
pipeline-cli training test <pipeline_name>
```

Runs the pipeline locally using a virtual environment and an experiment ID.

🔹 Run Docker smoke test

```bash
pipeline-cli training smoke-test <pipeline_name> --experiment-id <id>
```

Builds and runs the training pipeline inside a Docker container to ensure it works.

🔹 Deploy a training pipeline

```bash
pipeline-cli training deploy <pipeline_name>
```

Builds and pushes the Docker image, then updates the model version in Picsellia with Docker config.
