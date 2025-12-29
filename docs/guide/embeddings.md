# Computing Embeddings

Learn how to generate and work with embeddings in HyperView.

## Overview

HyperView uses **EmbedAnything** to compute high-dimensional embeddings from images. These embeddings capture semantic information about your images and are used to generate the 2D visualizations.

## Basic Usage

```python
import hyperview as hv

dataset = hv.Dataset("my_dataset")
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=1000)

# Compute embeddings
dataset.compute_embeddings(model="clip", show_progress=True)
```

## Embedding Models

### CLIP (Default)

CLIP (Contrastive Language-Image Pre-training) is the default model:

```python
dataset.compute_embeddings(model="clip")
```

**Advantages:**
- Strong semantic understanding
- Works well for diverse image types
- Good separation between classes
- Fast computation

**Use Cases:**
- General-purpose image datasets
- Multi-category classification
- Semantic search

### Custom Models

HyperView supports additional models through EmbedAnything. Check the [EmbedAnything documentation](https://github.com/StarlightSearch/EmbedAnything) for available models.

## Embedding Pipeline

### Step-by-Step Process

1. **Load Images**: Images are loaded from your dataset
2. **Preprocess**: Images are resized and normalized
3. **Encode**: Model generates high-dimensional vectors (e.g., 512 or 768 dimensions)
4. **Cache**: Embeddings are stored with each sample

### Performance Considerations

#### CPU vs GPU

```python
# EmbedAnything automatically uses GPU if available
dataset.compute_embeddings(model="clip")
```

**Performance:**
- **CPU**: ~100-200 images/second
- **GPU**: ~1000-2000 images/second

#### Batch Processing

For large datasets, embeddings are computed in batches:

```python
# Progress bar shows batches
dataset.compute_embeddings(show_progress=True)
```

## Caching Behavior

### Per-Sample Caching

Embeddings are cached at the sample level:

```python
# First run: computes all embeddings
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=500)
dataset.compute_embeddings()  # Computes 500 embeddings

# Second run: only computes new embeddings
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=1000)
dataset.compute_embeddings()  # Only computes 500 new embeddings
```

### Storage Location

For persistent datasets, embeddings are stored in:
```
~/.hyperview/lancedb/{dataset_name}/
```

### Recalculating Embeddings

To force recalculation, delete and recreate the dataset:

```python
# Delete old dataset
hv.Dataset.delete("my_dataset")

# Create new dataset
dataset = hv.Dataset("my_dataset")
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=1000)
dataset.compute_embeddings()
```

## Embedding Quality

### Checking Embeddings

```python
# Get a sample
sample = list(dataset.samples)[0]

# Check if embedding exists
if sample.embedding is not None:
    print(f"Embedding shape: {sample.embedding.shape}")
    print(f"Embedding type: {sample.embedding.dtype}")
    # Typical output: (512,) or (768,) float32
```

### Visualizing Embedding Distribution

```python
import numpy as np

# Collect all embeddings
embeddings = [s.embedding for s in dataset.samples if s.embedding is not None]
embeddings = np.array(embeddings)

print(f"Total embeddings: {len(embeddings)}")
print(f"Dimension: {embeddings.shape[1]}")
print(f"Mean: {embeddings.mean():.3f}")
print(f"Std: {embeddings.std():.3f}")
```

## From Embeddings to Visualization

### The Two-Step Process

```python
# Step 1: High-dimensional embeddings (e.g., 512D)
dataset.compute_embeddings(model="clip")

# Step 2: 2D projections
dataset.compute_visualization()
```

### Why Two Steps?

1. **Embeddings** capture semantic similarity in high dimensions
2. **Projections** reduce to 2D for human interpretation

The separation allows you to:
- Compute embeddings once
- Try different projection methods
- Reuse embeddings across visualizations

## Advanced Topics

### Memory Management

For large datasets, monitor memory usage:

```python
import psutil

# Check memory before
process = psutil.Process()
mem_before = process.memory_info().rss / 1024 / 1024  # MB

# Compute embeddings
dataset.compute_embeddings()

# Check memory after
mem_after = process.memory_info().rss / 1024 / 1024  # MB
print(f"Memory used: {mem_after - mem_before:.1f} MB")
```

### Embedding Dimension

Different models produce different embedding dimensions:

| Model | Dimension | Use Case |
|-------|-----------|----------|
| CLIP | 512 | General images |
| CLIP-Large | 768 | Higher quality |

### Custom Preprocessing

For specific use cases, you may want custom preprocessing:

```python
# This is handled by EmbedAnything automatically
# but you can configure it if needed
dataset.compute_embeddings(
    model="clip",
    # Additional model-specific parameters
)
```

## Troubleshooting

### Out of Memory Errors

If you encounter memory errors:

1. **Process in batches:**
```python
# Add samples incrementally
for i in range(0, 10000, 1000):
    dataset.add_from_huggingface(
        "dataset_name",
        max_samples=i+1000
    )
    dataset.compute_embeddings()
```

2. **Use a machine with more RAM**

3. **Use in-memory dataset for smaller subsets:**
```python
dataset = hv.Dataset("subset", persist=False)
dataset.add_from_huggingface("dataset_name", max_samples=500)
```

### Slow Computation

If embedding computation is slow:

1. **Check GPU availability:**
```python
import torch
print(f"GPU available: {torch.cuda.is_available()}")
```

2. **Reduce dataset size for testing:**
```python
dataset.add_from_huggingface("dataset_name", max_samples=100)
```

3. **Use a GPU instance** if processing large datasets

### Missing Dependencies

If you get import errors:

```bash
# Install embedding dependencies
pip install embed-anything
```

## Best Practices

1. **Compute once, use many times:**
   ```python
   # Compute embeddings
   dataset.compute_embeddings()
   
   # Save dataset
   dataset.save("dataset_with_embeddings.json")
   
   # Load in future sessions without recomputing
   dataset = hv.Dataset.load("dataset_with_embeddings.json")
   ```

2. **Start small:**
   ```python
   # Test with small subset
   dataset.add_from_huggingface("dataset_name", max_samples=100)
   dataset.compute_embeddings()
   
   # Scale up if successful
   dataset.add_from_huggingface("dataset_name", max_samples=10000)
   dataset.compute_embeddings()
   ```

3. **Monitor progress:**
   ```python
   # Always use progress bar for long operations
   dataset.compute_embeddings(show_progress=True)
   ```

## Next Steps

- [Visualization Guide](visualization.md) - Learn about 2D projections
- [Understanding Hyperbolic Space](../concepts/hyperbolic.md) - Why hyperbolic matters
- [Architecture Overview](../concepts/architecture.md) - How it all works together
