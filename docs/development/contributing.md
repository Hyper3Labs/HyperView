# Contributing to HyperView

Thank you for your interest in contributing to HyperView! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Node.js 18+ and npm
- Git

### Clone and Setup

```bash
# Clone the repository
git clone https://github.com/HackerRoomAI/HyperView.git
cd HyperView

# Create virtual environment
uv venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e ".[dev]"

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Verify Installation

```bash
# Check Python package
python -c "import hyperview; print(hyperview.__version__)"

# Run tests
pytest

# Run linter
ruff check .
```

## Development Workflow

### Making Changes

1. **Create a branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**

3. **Run tests:**
   ```bash
   pytest
   ```

4. **Run linter:**
   ```bash
   ruff check .
   ruff format .
   ```

5. **Commit your changes:**
   ```bash
   git add .
   git commit -m "Description of your changes"
   ```

6. **Push and create PR:**
   ```bash
   git push origin feature/your-feature-name
   ```

### Code Style

We use **Ruff** for linting and formatting:

```bash
# Check code
ruff check .

# Format code
ruff format .

# Fix auto-fixable issues
ruff check --fix .
```

**Configuration:** See `pyproject.toml` for Ruff settings.

### Testing

We use **pytest** for testing:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_dataset.py

# Run with coverage
pytest --cov=hyperview
```

**Test Structure:**
```
tests/
├── test_dataset.py      # Dataset operations
├── test_embeddings.py   # Embedding computation
├── test_server.py       # API endpoints
└── conftest.py          # Test fixtures
```

## Project Structure

```
HyperView/
├── src/hyperview/           # Main package
│   ├── core/               # Core classes
│   ├── embeddings/         # Embedding logic
│   ├── server/             # FastAPI server
│   └── cli.py              # CLI commands
├── frontend/               # Next.js frontend
│   ├── app/               # Pages and layouts
│   ├── components/        # React components
│   └── lib/               # Utilities
├── tests/                  # Test suite
├── scripts/               # Utility scripts
├── docs/                  # Documentation
└── pyproject.toml         # Python configuration
```

## Areas for Contribution

### 1. Core Features

- **New embedding models**: Add support for additional models
- **Custom projections**: Implement new projection algorithms
- **Dataset loaders**: Support more data sources
- **Export functionality**: Save selected subsets

### 2. Frontend

- **UI improvements**: Better layouts, accessibility
- **New visualizations**: Additional plot types
- **Performance**: Optimize for larger datasets
- **Mobile support**: Responsive design

### 3. Documentation

- **Tutorials**: Step-by-step guides
- **Examples**: Real-world use cases
- **API docs**: Detailed API reference
- **Translations**: Multi-language support

### 4. Testing

- **Unit tests**: Increase coverage
- **Integration tests**: End-to-end workflows
- **Performance tests**: Benchmark improvements

## Code Guidelines

### Python

1. **Follow PEP 8** (enforced by Ruff)
2. **Type hints** for function signatures:
   ```python
   def compute_embeddings(
       dataset: Dataset,
       model: str = "clip"
   ) -> None:
       ...
   ```
3. **Docstrings** for public APIs:
   ```python
   def launch(dataset: Dataset, port: int = 5151) -> None:
       """Launch the HyperView web interface.
       
       Args:
           dataset: Dataset to visualize
           port: Server port (default: 5151)
       """
       ...
   ```

### TypeScript/React

1. **Use TypeScript** for type safety
2. **Functional components** with hooks
3. **Descriptive names** for components and functions
4. **Comment complex logic**

### Git Commits

Use descriptive commit messages:

```
✅ Good:
- "Add support for custom embedding models"
- "Fix: Selection sync between grid and plot"
- "Docs: Add visualization guide"

❌ Bad:
- "Update code"
- "Fix bug"
- "Changes"
```

## Pull Request Process

1. **Describe your changes** clearly in PR description
2. **Link related issues** if applicable
3. **Ensure tests pass** (CI will check)
4. **Request review** from maintainers
5. **Address feedback** promptly
6. **Squash commits** if requested

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Performance improvement

## Testing
Describe how you tested your changes

## Checklist
- [ ] Code follows style guidelines
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] All tests pass
```

## Getting Help

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions or share ideas
- **Discord**: Join our community (link in README)

## Recognition

Contributors are recognized in:
- **CONTRIBUTORS.md** file
- **Release notes**
- **Project README**

Thank you for contributing to HyperView! 🚀
