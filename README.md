# 🧪 Picsellia Pipelines CLI

A command-line tool to create, test, deploy, and manage training and processing pipelines for [Picsellia](https://picsellia.com/).

Built with [Typer](https://typer.tiangolo.com/) for intuitive CLI usage.

---

## Installation

Install the CLI directly from GitHub (no need to clone the repo):

#### Using Poetry:

```bash
poetry add git+https://github.com/picselliahq/picsellia-pipelines-cli.git
```

#### Using uv (faster, works with requirements.txt or pyproject.toml):

```bash
uv pip install git+https://github.com/picselliahq/picsellia-pipelines-cli.git
```

You can now use:

```bash
pipeline-cli --help
```

## Available Commands
🔹 All CLI commands are structured like this:

```bash
pipeline-cli [init|test|deploy|smoke-test|sync] <pipeline_name>
```
The pipeline type is resolved automatically from its config file (config.toml), except during init.


## 🔧 Initialize a Pipeline

```bash
pipeline-cli init <pipeline_name> --type [training|processing] --template <template>
```

Examples:
```bash
pipeline-cli init yolov8 --type training --template ultralytics
pipeline-cli init resize-images --type processing --template simple
```

This generates:

- a `config.toml` with pipeline metadata

- a `Dockerfile`, `.dockerignore`, and dependency file (`pyproject.toml` or `requirements.txt`)

- scripts for both `picsellia_pipeline.py` and `local_pipeline.py`

- pre-filled `steps.py` and utility files

You can customize templates in your own extensions later.

### After Initialization

Once the pipeline is initialized:

- A local virtual environment is automatically created inside the pipeline directory (`<pipeline_name>/.venv`)
- You can directly activate it and run any pipeline-related commands:

```bash
cd <pipeline_name>
source .venv/bin/activate  # or .venv\Scripts\activate.bat on Windows
```

You can still use the CLI from inside the venv:
```bash
pipeline-cli test <pipeline_name>
```

## 🧪 Test Locally

```bash
pipeline-cli test <pipeline_name>
```

Runs the pipeline in a local virtualenv (.venv/) and prompts for required parameters (e.g., dataset version ID, experiment ID, etc.).

You’ll need to export the following environment variables before running:

```bash
export API_TOKEN="your-picsellia-token"
export ORGANIZATION_NAME="your-org-name"
```

```bash
export HOST="https://app.picsellia.com"
```

## 🔥 Smoke Test in Docker

```bash
pipeline-cli smoke-test <pipeline_name>
```

Builds the Docker image for the pipeline and runs it locally to validate that everything (code + dependencies + env) works inside the container.


## 🚀 Deploy to Picsellia

```bash
pipeline-cli deploy <pipeline_name>
```

Builds and pushes the Docker image to your configured registry and registers the pipeline in Picsellia (either as a training pipeline or a dataset processing job).

## 🔁 Sync Parameters (Processing Only)

```bash
pipeline-cli sync <pipeline_name>

```

For processing pipelines, this updates the default parameters stored in Picsellia based on your Parameters class and config.toml.

Training sync is not yet implemented.

## 📁 Project Structure Example

```bash
resize-images/
├── config.toml
├── Dockerfile
├── picsellia_pipeline.py
├── local_pipeline.py
├── steps.py
├── utils/
│   ├── parameters.py
│   └── processing.py
└── pyproject.toml
```

## 💡 Tips

- You can override the output directory on init with --output-dir
- Virtual environments are created in `<pipeline_name>/.venv` by default
- It's recommended to `cd <pipeline_name>` after init to work from inside the folder
- You can always edit config.toml to change pipeline metadata or execution scripts

--------------------------------

Made with ❤️ by the Picsellia team.
