# Picsellia Pipelines CLI

The Picsellia Pipelines CLI is the fastest way for Picsellia users to create, test, dockerize, deploy, and manage their own custom processing or training pipelines.

It streamlines the entire development workflow:

1. Start from a ready-to-use template

2. Run and debug your pipeline locally

3. Validate the Docker image

4. Deploy it to your Picsellia organization

5. Optionally launch real jobs directly from the CLI

This removes the need to manually handle Docker builds, API interactions, or complex job setup — the CLI takes care of everything for you.

Built with [Typer](https://typer.tiangolo.com/) for an intuitive command-line experience.

---

## 💡 Mental model

Think of a pipeline as:

- a Python function (`pipeline.py`)

- calling one or more steps (`steps.py`)

- parameterized by a config file (`run_config.toml`)

- executed either locally or on Picsellia infrastructure

## Quick Workflow Overview

If you're new to the Picsellia Pipelines CLI, here’s the complete workflow in **5 essential steps:**

1. **Initialize a pipeline project** → generates code, config, Dockerfile

   👉 See [Init — Create a New Pipeline](#-init--create-a-new-pipeline)


2. **Customize your pipeline** → implement steps in `steps.py` and parameters in `utils/parameters.py`

   👉 See [Customize Your Pipeline — Add Steps & Parameters](#-customize-your-pipeline--add-steps--parameters)


3. **Test locally in Python** → confirm your code works

   👉 See [Test — Run Your Pipeline Locally](#-test--run-your-pipeline-locally)


4. **Smoke test in Docker** → validate the full container environment

   👉 See [Smoke Test — Validate the Docker Runtime](#-smoke-test--validate-the-docker-runtime)


5. **Deploy to Picsellia** → build + push Docker image + register pipeline

   👉 See [Deploy — Publish Your Pipeline to Picsellia](#-deploy--publish-your-pipeline-to-picsellia)


6. (Optionally) **Launch real jobs from the CLI**

   👉 See [Launch — Run Your Pipeline on Picsellia’s Infrastructure](#-launch--run-your-pipeline-on-picsellias-infrastructure)

This workflow ensures your pipeline is fully validated before going to production.

## Installation

<details>
<summary>Show installation instructions</summary>


#### With uv (recommended)

```bash
uv pip install picsellia-pipelines-cli
```

#### With Poetry:

```bash
poetry add picsellia-pipelines-cli
```

Check installation:

```bash
pxl-pipeline --help
```
</details>

## 🔐 Authentication

**Objective: Use the same Picsellia user and environment across all commands**

```bash
pxl-pipeline login
```

<details>
<summary>Show detailed explanation</summary>

This stores your:

- organization
- environment (PROD / BETA / DEV / CUSTOM)
- API token
- optional custom base URL

Other helpful commands:

```bash
pxl-pipeline whoami   # show active context
pxl-pipeline switch   # change organization/environment
pxl-pipeline logout   # clear active context
```
</details>

## 🔧 Init — Create a new pipeline

**Objective: Generate a ready-to-use pipeline project folder with all required template files**

```bash
pxl-pipeline init <pipeline_name> --type [training|processing] --template <template_name>
```

<details>
<summary>Show detailed explanation</summary>

Examples:
```bash
pxl-pipeline init yolov8 --type training --template yolov8
pxl-pipeline init resize-images --type processing --template dataset_version_creation
```

This generates:

- a single entrypoint: `pipeline.py`

- `config.toml` (metadata + execution parameters)

- `Dockerfile` and `.dockerignore`

- a consistent folder structure:

```bash
my-pipeline/
├── pipeline.py
├── steps.py
├── utils/
│   ├── parameters.py
├── config.toml
├── Dockerfile
├── .dockerignore
├── runs/
│   └── run_config.toml   # template for test/smoke-test/launch
└── pyproject.toml
```

You're now ready to implement your custom logic.

</details>

## ✏️ Customize your pipeline — Add steps & parameters

**Objective: Adapt the pipeline template to your specific use case**

After running `init`, your pipeline project is generated with a default structure:

- `pipeline.py` — your entrypoint

- `steps.py` (a default process step) — implement processing or training steps

- `utils/parameters.py` — define your pipeline parameters

👉 In most cases, if you chose the right template, you only need to modify the existing `process` step to implement your use case.

You do not need to redesign the whole pipeline unless your logic is more advanced.

### Recommended approach

1. Start by editing the existing `process` step

    This step already exposes the correct inputs, outputs, and parameters expected by Picsellia.

2. Only add new steps if needed

   If your pipeline requires additional logic (pre-processing, post-processing, custom validation, chaining operations, etc.), you can:

   - modify the existing step
   - replace it entirely
   - or add new steps and compose them in `pipeline.py`

### Working with Steps

<details>
<summary>Show detailed explanation</summary>

Steps are Python functions decorated with `@step`.
You can define them in `steps.py` and call them freely inside `pipeline.py`.

Example (`steps.py`):

```python
from picsellia_pipeline.core import step

@step
def process(dataset_input, dataset_output):
    # your processing logic here
    dataset_output["images"] = [img.upper() for img in dataset_input["images"]]
    return dataset_output
```

Example pipeline (`pipeline.py`):

```python
from steps import process
from picsellia_pipeline.core import pipeline, step

@pipeline
def dataset_version_creation_pipeline():
    dataset_collection = load_coco_datasets()
    dataset_collection["output"] = process(
        dataset_collection["input"], dataset_collection["output"]
    )
    upload_full_dataset(dataset_collection["output"], use_id=False)
    return dataset_collection
```
</details>

### Adding Parameters

<details>
<summary>Show detailed explanation</summary>

Define pipeline parameters in `utils/parameters.py`.

All parameters declared here are:

- automatically detected by the CLI

- injected at runtime

- uploaded to Picsellia during deploy or sync

Example:

```python
from picsellia.types.schemas import LogDataType
from picsellia_cv_engine.core.parameters import Parameters

class ProcessingParameters(Parameters):
    def __init__(self, log_data: LogDataType):
        super().__init__(log_data=log_data)
        self.datalake = self.extract_parameter(["datalake"], expected_type=str, default="default")
        self.data_tag = self.extract_parameter(["data_tag"], expected_type=str, default="processed")
```

Each parameter requires:

- a key → used as the parameter name on the Picsellia platform

- an expected type → str, int, float, etc.

- a default value → mandatory for parameter registration

Once parameters are defined, you can reference them directly in your step logic and override their values in `run_config.toml`.


</details>

## 🧪 Test — Run your pipeline locally

**Objective: Ensure your Python code works exactly as expected, using real Picsellia objects**

```bash
pxl-pipeline test <pipeline_name> --run-config-file <path>
```

<details>
<summary>Show detailed explanation</summary>

#### ⚠️ Important
Even though the pipeline runs locally, all datasets, experiments, and outputs are created and updated on the Picsellia platform.

This command:

- runs the pipeline locally in the virtual env (.venv/)
- loads the configuration from your run_config.toml
- interacts with real Picsellia objects
- uploads results to the platform exactly like a real run
- guarantees your step logic and parameters behave correctly

A template run config is generated automatically at:

```bash
<pipeline_name>/runs/run_config.toml
```

You simply need to fill it with your dataset/model IDs, parameters, or metadata.

Example (dataset version creation processing):

```toml
override_outputs = true

[job]
type = "DATASET_VERSION_CREATION"

[input.dataset_version]
id = ""

[output.dataset_version]
name = "test_my_pipeline"

[parameters]
datalake = "default"
data_tag = "processed"
```

Once the file is filled:

```bash
pxl-pipeline test my-pipeline \
  --run-config-file my-pipeline/runs/run_config.toml
```

</details>

## 🔥 Smoke Test — Validate the Docker runtime

**Objective: Ensure your Dockerfile, dependencies, imports, paths, and runtime fully work before deployment**

```bash
pxl-pipeline smoke-test <pipeline_name> --run-config-file <path>
```

<details>
<summary>Show detailed explanation</summary>

This command:

1. Builds the Docker image
2. Runs the pipeline inside the container (not Python locally)
3. Uses the same run_config.toml as the test command
4. Updates real objects/results on Picsellia

It is your final validation step before deployment.

A successful smoke test strongly indicates that the pipeline will run properly on Picsellia’s infrastructure.

</details>

## 🚀 Deploy — Publish your pipeline to Picsellia

**Objective: Build, version, push the Docker image, and register/update the pipeline in your organization**

```bash
pxl-pipeline deploy <pipeline_name>
```

<details>
<summary>Show detailed explanation</summary>

This command:

- builds the Docker image
- pushes it to your configured registry
- versions the image
- creates or updates the Picsellia processing or training asset
- ensures the pipeline is ready to be launched from the UI

After deployment, the pipeline becomes usable by your team in the Picsellia interface.

</details>

## 🟢 Launch — Run your pipeline on Picsellia’s infrastructure

*(Optional)*

**Objective: Trigger a real Picsellia job (not local), using the same `run_config.toml`**

```bash
pxl-pipeline launch <pipeline_name> --run-config-file <path>
```

<details>
<summary>Show detailed explanation</summary>

Launch behaves like:

- launching a processing job on a dataset
- or launching a training experiment
- without manually creating an experiment or job in the UI

The `run_config.toml` defines:

- the dataset/model input
- the output dataset or experiment name
- the pipeline parameters

This is equivalent to triggering an actual job from the Picsellia UI.

</details>

## 🔁 Sync — Synchronize local parameters with Picsellia

*(Optional)*

**Objective: Update parameters stored on Picsellia to match your local**

```bash
pxl-pipeline sync <pipeline_name>
```

<details>
<summary>Show detailed explanation</summary>

For processing pipelines, this syncs:

- default parameter values
- parameter schema / types

Sync is usually unnecessary if you run:

```bash
pxl-pipeline deploy
```

because deploy already updates the parameter definition on the platform.

Training sync is not yet implemented.

</details>

## 💡 Tips

- Use `--output-dir` during init to generate the pipeline elsewhere
- Virtual environments are created in `<pipeline>/.venv`
- You can edit `config.toml` at any time (metadata, entrypoints, dependencies)
- Always run `test` → `smoke-test` → `deploy` for a clean workflow
- A successful smoke test almost guarantees a successful production run

--------------------------------

Made with ❤️ by the Picsellia team.
