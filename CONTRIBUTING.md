# Contributing to HyperView

We welcome contributions! This guide will help you set up your development environment and submit high-quality pull requests.

## Development Setup

### Requirements
- **Python 3.10+**
- **uv** (Package manager)
- **Node.js** (For frontend development)

### One-time Setup
Clone the repo and install dependencies:

```bash
git clone https://github.com/Hyper3Labs/HyperView.git
cd HyperView

# Create virtual environment and install dev dependencies
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Install frontend dependencies
cd frontend
npm install
cd ..
```

## Running Locally

For the best development experience, run the backend and frontend in separate terminals.

### 1. Start the Backend
Runs the Python API server at `http://127.0.0.1:6262`.

```bash
uv run hyperview demo --samples 200 --no-browser
```

_Tip: Use `HF_DATASETS_OFFLINE=1` if you have cached datasets and want to work offline._

### 2. Start the Frontend
Runs the Next.js dev server at `http://127.0.0.1:3000` with hot reloading.

```bash
cd frontend
npm run dev
```

The frontend automatically proxies API requests (`/api/*`) to the backend.

## Common Tasks

### Testing & Linting
Please ensure all checks pass before submitting a PR.

```bash
# Python
uv run pytest             # Run unit tests
uv run ruff format .      # formatting
uv run ruff check . --fix # Linting

# Frontend
cd frontend
npm run lint
```

### Exporting the Frontend
The Python package bundles the compiled frontend. If you modify the frontend, you must regenerate the static assets so they can be served by the Python backend in production/demos.

```bash
bash scripts/export_frontend.sh
```
_This compiles the frontend and places artifacts into `src/hyperview/server/static/`. Do not edit files in that directory manually._

## Pull Request Guidelines

1.  **Scope**: Keep changes focused. Open an issue first for major refactors or new features.
2.  **Tests**: Add tests for new logic where practical.
3.  **Visuals**: If changing the UI, please attach a screenshot or GIF to your PR.
4.  **Format**: Ensure code is formatted with `ruff` (Python) and `prettier` (JS/TS implicit in `npm run lint`).
