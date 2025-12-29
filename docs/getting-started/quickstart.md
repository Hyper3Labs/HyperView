# Quick Start

This guide will help you get started with HyperView in just a few minutes.

## Run the Demo

The fastest way to see HyperView in action is to run the built-in demo:

```bash
hyperview demo --samples 500
```

This will:

1. Load 500 samples from the CIFAR-100 dataset
2. Compute CLIP embeddings for each image
3. Generate both Euclidean and Hyperbolic 2D visualizations
4. Start the web server at **http://127.0.0.1:5151**

Your browser will automatically open to show the interactive visualization!

## Your First Dataset

Let's create a simple dataset from scratch:

### Step 1: Create a Dataset

```python
import hyperview as hv

# Create a new dataset
dataset = hv.Dataset("my_first_dataset")
```

### Step 2: Add Data

You can add data from multiple sources:

#### From HuggingFace

```python
dataset.add_from_huggingface(
    "uoft-cs/cifar100",
    split="train",
    max_samples=1000
)
```

#### From Local Directory

```python
# Assumes folder structure: /images/{label}/{image_files}
dataset.add_images_dir(
    "/path/to/images",
    label_from_folder=True
)
```

### Step 3: Compute Embeddings

```python
# Generate high-dimensional embeddings using CLIP
dataset.compute_embeddings(model="clip", show_progress=True)
```

This step uses the EmbedAnything library to compute CLIP embeddings for your images.

### Step 4: Compute Visualizations

```python
# Generate 2D projections (Euclidean and Hyperbolic)
dataset.compute_visualization()
```

This creates:
- **Euclidean projection**: Standard UMAP projection
- **Hyperbolic projection**: Poincaré disk representation

### Step 5: Launch the UI

```python
# Start the interactive viewer
hv.launch(dataset)
```

This will open **http://127.0.0.1:5151** in your browser!

## Complete Example

Here's the complete code:

```python
import hyperview as hv

# Create dataset
dataset = hv.Dataset("my_first_dataset")

# Load data from HuggingFace
dataset.add_from_huggingface(
    "uoft-cs/cifar100",
    split="train",
    max_samples=1000
)

# Compute embeddings
dataset.compute_embeddings(model="clip", show_progress=True)

# Compute visualizations
dataset.compute_visualization()

# Launch the UI
hv.launch(dataset)
```

## Save and Load Datasets

### Save Your Work

```python
# Save dataset with embeddings
dataset.save("my_dataset.json")
```

This saves:
- Dataset metadata
- Sample information
- Embeddings (if computed)
- Visualization coordinates

### Load Later

```python
# Load a previously saved dataset
dataset = hv.Dataset.load("my_dataset.json")

# Launch the viewer
hv.launch(dataset)
```

## Understanding the UI

The HyperView interface has two main panels:

### Left Panel: Image Grid
- Browse all images in your dataset
- Select images by clicking
- Filter by labels

### Right Panel: Scatter Plot
- **Euclidean view**: Standard 2D projection
- **Hyperbolic view**: Poincaré disk visualization
- Toggle between views using the button
- Click points to select corresponding images
- Drag to pan (in Hyperbolic mode)

### Selection Sync
- Selecting images in the grid highlights them in the plot
- Selecting points in the plot highlights corresponding images
- **Bidirectional selection** keeps both views in sync

## Next Steps

Now that you've created your first dataset, learn more about:

- [Working with Datasets](../guide/datasets.md) - Advanced dataset operations
- [Computing Embeddings](../guide/embeddings.md) - Different embedding models
- [Visualization Options](../guide/visualization.md) - Customizing visualizations
- [Why Hyperbolic Space?](../concepts/hyperbolic.md) - Understanding the mathematics

## CLI Reference

### Demo Command

```bash
hyperview demo [OPTIONS]
```

Options:
- `--samples N`: Number of samples to load (default: 500)
- `--no-browser`: Don't open browser automatically
- `--port PORT`: Specify custom port (default: 5151)

### Examples

```bash
# Load 1000 samples
hyperview demo --samples 1000

# Run without opening browser
hyperview demo --samples 500 --no-browser

# Use custom port
hyperview demo --samples 500 --port 8080
```
