# HyperView Documentation

This directory contains the documentation for HyperView, built with [MkDocs](https://www.mkdocs.org/) and the [Material theme](https://squidfunk.github.io/mkdocs-material/).

## Documentation Website

The documentation is hosted on GitHub Pages at:

**https://hackerroomai.github.io/HyperView**

## Local Development

### Prerequisites

- Python 3.10+
- pip

### Setup

Install MkDocs and dependencies:

```bash
pip install mkdocs-material
```

### Preview Locally

Serve the documentation with live reload:

```bash
mkdocs serve
```

Then open http://127.0.0.1:8000 in your browser.

### Build

Build the static site:

```bash
mkdocs build
```

Output is in the `site/` directory.

## Structure

```
docs/
├── index.md                    # Home page
├── getting-started/
│   ├── installation.md        # Installation guide
│   ├── quickstart.md          # Quick start tutorial
│   └── api.md                 # Python API overview
├── guide/
│   ├── datasets.md            # Working with datasets
│   ├── embeddings.md          # Computing embeddings
│   └── visualization.md       # Visualization guide
├── concepts/
│   ├── hyperbolic.md          # Why hyperbolic space
│   └── architecture.md        # System architecture
├── demo.md                     # Interactive demo
├── demo.html                   # Interactive Poincaré disk demo
├── api-reference.md            # Complete API reference
├── development/
│   ├── contributing.md        # Contributing guide
│   └── frontend.md            # Frontend development
└── assets/                     # Images and resources
```

## Configuration

Documentation configuration is in `mkdocs.yml` at the project root.

Key settings:
- `site_name`: HyperView
- `theme`: material
- `repo_url`: https://github.com/HackerRoomAI/HyperView
- `site_url`: https://hackerroomai.github.io/HyperView

## Deployment

Documentation is automatically deployed to GitHub Pages when changes are pushed to the `main` branch via GitHub Actions.

### Manual Deployment

If you need to deploy manually:

```bash
# Build the site
mkdocs build

# Deploy to GitHub Pages
mkdocs gh-deploy
```

This will:
1. Build the documentation
2. Push to the `gh-pages` branch
3. GitHub Pages will serve the site

## GitHub Pages Setup

To enable GitHub Pages for this repository:

1. Go to repository **Settings** > **Pages**
2. Under **Source**, select:
   - **Source**: GitHub Actions (recommended)
   - The workflow in `.github/workflows/docs.yml` will handle deployment

Alternatively, you can use the `gh-pages` branch:
1. Select **Deploy from a branch**
2. Choose **gh-pages** branch
3. Select **/ (root)** folder

The site will be available at: **https://hackerroomai.github.io/HyperView**

## Custom Domain (Optional)

To use a custom domain:

1. Add a `CNAME` file to the `docs/` directory:
   ```
   docs.hyperview.ai
   ```

2. Configure DNS:
   - Add a CNAME record pointing to `hackerroomai.github.io`

3. Update `site_url` in `mkdocs.yml`:
   ```yaml
   site_url: https://docs.hyperview.ai
   ```

## Contributing

To contribute to the documentation:

1. Edit files in the `docs/` directory
2. Preview locally with `mkdocs serve`
3. Commit and push changes
4. Documentation will be automatically deployed

For more details, see [Contributing Guide](development/contributing.md).

## Writing Documentation

### Markdown Features

MkDocs with Material theme supports:

- **Code blocks** with syntax highlighting
- **Admonitions** (notes, warnings, etc.)
- **Tables**
- **Math** (LaTeX)
- **Diagrams** (Mermaid)
- **Tabs**
- **Icons and emojis**

### Examples

#### Code Block

\`\`\`python
import hyperview as hv
dataset = hv.Dataset("my_dataset")
\`\`\`

#### Admonition

!!! note
    This is a note admonition.

!!! warning
    This is a warning admonition.

#### Math

Inline: $E = mc^2$

Block:
$$
d(u, v) = \text{arccosh}\left(1 + 2 \frac{\|u - v\|^2}{(1 - \|u\|^2)(1 - \|v\|^2)}\right)
$$

## Resources

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [Markdown Guide](https://www.markdownguide.org/)
- [GitHub Pages Documentation](https://docs.github.com/en/pages)
