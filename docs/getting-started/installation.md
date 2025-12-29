# Installation

## Requirements

- Python 3.10 or higher
- pip or uv package manager

## Install from PyPI (Recommended)

```bash
pip install hyperview
```

## Install from Source

If you want to contribute or use the latest development version:

```bash
# Clone the repository
git clone https://github.com/HackerRoomAI/HyperView.git
cd HyperView

# Using uv (recommended)
uv venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .

# Or using pip
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

## Optional Dependencies

### Hyperbolic Operations

For advanced hyperbolic operations, install with the hyperbolic extras:

```bash
pip install hyperview[hyperbolic]
```

This installs:
- PyTorch >= 2.0.0
- Geoopt >= 0.5.1

### Development Tools

For development and testing:

```bash
pip install hyperview[dev]
```

This installs:
- pytest >= 8.0.0
- pytest-asyncio >= 0.24.0
- httpx >= 0.27.0
- ruff >= 0.7.0

## Verify Installation

After installation, verify that HyperView is installed correctly:

```bash
hyperview --version
```

Or in Python:

```python
import hyperview as hv
print(hv.__version__)
```

## System Requirements

### Minimal Setup

- **RAM**: 4GB minimum (8GB recommended)
- **Storage**: 500MB for installation + dataset storage
- **CPU**: Any modern CPU with AVX support

### For Large Datasets

- **RAM**: 16GB+ recommended
- **Storage**: Depends on dataset size (embeddings are cached)
- **GPU**: Optional, but recommended for faster embedding computation

## Troubleshooting

### Import Errors

If you encounter import errors, ensure you've activated your virtual environment:

```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Embedding Computation Fails

If embedding computation fails, ensure you have enough RAM and disk space. For large datasets, consider:

- Processing in smaller batches
- Using a machine with more RAM
- Installing the GPU version of dependencies

### Port Already in Use

If port 5151 is already in use, you can specify a different port:

```python
hv.launch(dataset, port=8080)
```

## Next Steps

- [Quick Start Tutorial](quickstart.md)
- [Python API Guide](api.md)
- [Working with Datasets](../guide/datasets.md)
