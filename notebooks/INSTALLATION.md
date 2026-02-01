# Installation Instructions

This guide shows how to set up and run the demo notebook in VSCode.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) package manager installed
- VSCode with Python extension

## Setup Steps

### 1. Initialize the Project

```bash
uv init
```

This creates a new project named `hyperview-demo-notebook`.

### 2. Create Virtual Environment

```bash
uv venv .venv
```

This creates a virtual environment using Python 3.13.2 in the `.venv` directory.

### 3. Activate Virtual Environment

```bash
source .venv/bin/activate
```

Your terminal prompt should now show `(.venv)` at the beginning.

### 4. Install Required Packages

Install the packages in the following order:

```bash
uv pip install ipykernel
```

```bash
uv pip install jupyter
```

```bash
uv pip install hyperview
```

**Note:** Do not use commas between package names when installing multiple packages at once. Use spaces instead or install packages separately.

## Verify Installation

After installation, you should have:

- Jupyter notebook support (68+ packages)
- IPython kernel for running notebooks (30+ packages)
- Hyperview and dependencies (59+ packages)

## Running the Notebook

1. Open the notebook file in VSCode
2. Select the Python interpreter from `.venv` when prompted
3. Run the notebook cells

## Troubleshooting

### Virtual Environment Not Activating

If you see "no such file or directory" when activating, check the path:

```bash
source .venv/bin/activate
```

Make sure you typed `activate` correctly (not `acticate`).

### Package Installation Errors

If you get parsing errors during installation, avoid using commas in the package list. Install packages separately or use spaces to separate package names.
