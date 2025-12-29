# Visualization

Learn how to generate and customize visualizations in HyperView.

## Overview

HyperView provides two types of 2D visualizations:

1. **Euclidean projection**: Standard UMAP projection to flat 2D space
2. **Hyperbolic projection**: Projection to the Poincaré disk (hyperbolic space)

## Basic Usage

```python
import hyperview as hv

# Create and prepare dataset
dataset = hv.Dataset("my_dataset")
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=1000)
dataset.compute_embeddings()

# Generate visualizations
dataset.compute_visualization()

# Launch the viewer
hv.launch(dataset)
```

## Visualization Types

### Euclidean Projection (UMAP)

The Euclidean view uses UMAP to project high-dimensional embeddings to 2D Euclidean space.

**Characteristics:**
- Points distributed in a flat 2D plane
- Familiar scatter plot layout
- Good for general exploration

**Use Cases:**
- Initial data exploration
- Finding broad clusters
- Standard dimensionality reduction

### Hyperbolic Projection (Poincaré Disk)

The hyperbolic view projects embeddings onto the Poincaré disk model of hyperbolic space.

**Characteristics:**
- Points arranged on a circular disk
- Space expands exponentially toward the edge
- Minority and rare classes pushed outward
- Prevents representation collapse

**Use Cases:**
- Hierarchical data
- Long-tail distributions
- Identifying rare subgroups
- Preventing minority class collapse

## Interactive Features

### The Dual-Panel Interface

When you launch the viewer, you get two synchronized panels:

#### Left Panel: Image Grid
- Browse all images
- Click to select
- Filter by labels
- Paginated view

#### Right Panel: Scatter Plot
- Toggle between Euclidean/Hyperbolic
- Click points to select images
- Drag to pan (Hyperbolic mode only)
- Zoom and explore

### Bidirectional Selection

Selections are synchronized between both views:

```
Select image in grid → Point highlighted in plot
Select point in plot → Image highlighted in grid
```

This makes it easy to:
- Identify which images form clusters
- Find images in specific regions
- Explore outliers and rare cases

## Understanding the Poincaré Disk

### Geometry Basics

The Poincaré disk represents hyperbolic space within a unit circle:

- **Center**: Origin point (0, 0)
- **Interior**: All points with distance < 1 from origin
- **Boundary**: Circle at distance = 1 (infinitely far away)

### Space Expansion

As you move toward the edge:
- Space expands exponentially
- More "room" for points
- Distances grow rapidly

This is why minority classes appear at the edge - they have space to remain distinct!

### Navigation

In Hyperbolic mode:

**Drag to Pan:**
- Click and drag to move around
- Points shift according to hyperbolic geometry
- Notice how edge points expand as you bring them to center

**Why Navigation Matters:**
- Bring edge clusters to center for detailed inspection
- Experience the "infinite" space property
- See how rare classes separate when given room

## Visualization Pipeline

### The Complete Process

```python
# 1. Create dataset and add samples
dataset = hv.Dataset("my_dataset")
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=1000)

# 2. Compute high-dimensional embeddings (e.g., 512D)
dataset.compute_embeddings(model="clip")

# 3. Generate 2D projections
dataset.compute_visualization()

# Result: Each sample now has:
#   - High-D embedding (512D)
#   - Euclidean 2D coordinates (x, y)
#   - Hyperbolic 2D coordinates (x, y) on Poincaré disk
```

### Regenerating Visualizations

When you add more samples, visualizations need to be recomputed:

```python
# Initial visualization
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=500)
dataset.compute_embeddings()
dataset.compute_visualization()

# Add more samples
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=1000)
dataset.compute_embeddings()  # Only computes 500 new embeddings
dataset.compute_visualization()  # Recomputes ALL projections
```

**Why recompute all projections?**
- UMAP requires fitting on the complete dataset
- Hyperbolic projection depends on the full distribution

## Customization

### Launching with Custom Settings

```python
# Custom port
hv.launch(dataset, port=8080)

# Custom host
hv.launch(dataset, host="0.0.0.0", port=8080)

# Don't auto-open browser
hv.launch(dataset, open_browser=False)
```

### Color Schemes

Colors are automatically assigned to labels based on the dataset:

```python
# Check assigned colors
print(dataset.labels)  # ['cat', 'dog', 'bird']
# Colors are assigned automatically
```

## Performance Considerations

### Dataset Size

| Size | Euclidean | Hyperbolic | Recommended |
|------|-----------|------------|-------------|
| < 1K samples | Instant | Instant | Both work great |
| 1K - 10K | < 1 min | < 1 min | Both work well |
| 10K - 100K | 2-5 min | 2-5 min | Consider subsampling for exploration |
| > 100K | 10+ min | 10+ min | Use subsampling or incremental approach |

### Browser Performance

The web interface handles up to 10,000 points smoothly. For larger datasets:

1. **Pagination**: Images are paginated automatically
2. **WebGL**: Scatter plot uses hardware acceleration
3. **Lazy Loading**: Images loaded on-demand

## Visual Comparison

### Euclidean vs Hyperbolic

Compare the two views to understand representation collapse:

**Euclidean (Flat Space):**
- Majority class dominates the center
- Minority classes compressed
- Rare cases often overlapping with minority
- Limited space at boundaries

**Hyperbolic (Curved Space):**
- Majority still at center
- Minority classes have more space
- Rare cases distinct at edge
- "Infinite" space at boundaries

### The Collapse Phenomenon

Toggle between views in the UI to see:

1. **In Euclidean**: Rare cases crushed together
2. **In Hyperbolic**: Same cases spread out and distinct

This visual difference is the core insight of HyperView!

## Use Cases

### 1. Dataset Exploration

```python
# Quick exploration
dataset = hv.Dataset("explore")
dataset.add_from_huggingface("dataset_name", max_samples=500)
dataset.compute_embeddings()
dataset.compute_visualization()
hv.launch(dataset)
```

**What to Look For:**
- Cluster structure
- Class separation
- Outliers and anomalies
- Label errors

### 2. Quality Control

```python
# Identify problematic samples
# 1. Launch viewer
# 2. Look for outliers (points far from their class)
# 3. Select and inspect
# 4. Remove or relabel as needed
```

### 3. Long-Tail Analysis

```python
# Find rare subgroups
# 1. Switch to Hyperbolic view
# 2. Pan to edge regions
# 3. Identify rare clusters
# 4. Select and export
```

### 4. Class Balance

```python
# Visualize class distribution
# 1. Note positions in both views
# 2. See which classes are at edge (underrepresented)
# 3. Make informed sampling decisions
```

## Troubleshooting

### Projections Look Random

If your projections look random or lack structure:

1. **Check embeddings:**
   ```python
   sample = list(dataset.samples)[0]
   print(sample.embedding)  # Should not be None
   ```

2. **Ensure you computed embeddings first:**
   ```python
   dataset.compute_embeddings()  # MUST be called before visualization
   dataset.compute_visualization()
   ```

3. **Try more samples:**
   ```python
   # UMAP works better with more data
   dataset.add_from_huggingface("dataset_name", max_samples=1000)
   ```

### Browser Won't Load

If the web interface fails to load:

1. **Check server logs** in terminal
2. **Try different port:**
   ```python
   hv.launch(dataset, port=8080)
   ```
3. **Check firewall settings**

### Slow Rendering

If the scatter plot is laggy:

1. **Reduce visible points** (use pagination)
2. **Close other browser tabs**
3. **Try a different browser** (Chrome/Edge recommended)

## Next Steps

- [Understanding Hyperbolic Space](../concepts/hyperbolic.md) - Learn the mathematics
- [Architecture Overview](../concepts/architecture.md) - How the system works
- [Interactive Demo](../demo.md) - Try the live demo
