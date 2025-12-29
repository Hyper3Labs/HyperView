# Working with Datasets

This guide covers advanced dataset operations in HyperView.

## Creating a Dataset

### Persistent Datasets

By default, datasets are persistent and stored on disk:

```python
import hyperview as hv

# Persistent dataset - survives restarts
dataset = hv.Dataset("my_dataset")
```

**Storage location:** `~/.hyperview/lancedb/` (configurable via `HYPERVIEW_DATABASE_DIR` environment variable)

### In-Memory Datasets

For temporary work or testing, create an in-memory dataset:

```python
# In-memory dataset - lost when process exits
dataset = hv.Dataset("temp_dataset", persist=False)
```

## Adding Samples

### From HuggingFace

Load datasets directly from HuggingFace Hub:

```python
dataset.add_from_huggingface(
    "uoft-cs/cifar100",
    split="train",
    image_key="img",
    label_key="fine_label",
    max_samples=1000,
)
```

**Common HuggingFace Datasets:**

```python
# CIFAR-100
dataset.add_from_huggingface("uoft-cs/cifar100", split="train")

# ImageNet (requires authentication)
dataset.add_from_huggingface("imagenet-1k", split="validation")

# Fashion MNIST
dataset.add_from_huggingface("fashion_mnist", split="train")
```

### From Local Directory

Load images from your local filesystem:

```python
dataset.add_images_dir("/path/to/images", label_from_folder=True)
```

**Expected Structure:**

When `label_from_folder=True`, organize images by label:

```
/path/to/images/
├── cat/
│   ├── cat001.jpg
│   ├── cat002.jpg
│   └── ...
├── dog/
│   ├── dog001.jpg
│   ├── dog002.jpg
│   └── ...
└── bird/
    ├── bird001.jpg
    └── ...
```

**Without Labels:**

```python
# All images get the same label or no label
dataset.add_images_dir("/path/to/images", label_from_folder=False)
```

## Persistence Model: Additive

HyperView uses an **additive** persistence model. This means:

- **Samples are never implicitly deleted**
- **New samples are always added**
- **Existing samples are preserved**

### Behavior Table

| Action | Behavior |
|--------|----------|
| Add samples | New samples inserted, existing skipped by ID |
| Request fewer than exist | Existing samples preserved (no deletion) |
| Request more than exist | Only new samples added |
| Embeddings | Cached per-sample, reused across sessions |
| Projections | Recomputed when new samples added (UMAP requires refit) |

### Example: Growing a Dataset

```python
dataset = hv.Dataset("my_dataset")

# Add 200 samples
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=200)
print(len(dataset))  # 200 samples

# Request 400 samples - adds 200 new samples
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=400)
print(len(dataset))  # 400 samples

# Request 300 samples - no change (already have 400)
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=300)
print(len(dataset))  # 400 samples

# Request 500 samples - adds 100 new samples
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=500)
print(len(dataset))  # 500 samples
```

### Explicit Deletion

To remove a dataset entirely, use the `delete()` class method:

```python
hv.Dataset.delete("my_dataset")
```

⚠️ **Warning:** This permanently deletes the dataset and all associated data (samples, embeddings, projections).

## Computing Embeddings

### High-Dimensional Embeddings

Generate embeddings using CLIP (or other models):

```python
# Compute embeddings with progress bar
dataset.compute_embeddings(model="clip", show_progress=True)
```

**Key Points:**

- Embeddings are **cached per-sample**
- If a sample already has embeddings, it's **skipped**
- This makes incremental updates efficient

**Example: Adding More Samples**

```python
# Initial computation
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=100)
dataset.compute_embeddings()  # Computes 100 embeddings

# Add more samples
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=200)
dataset.compute_embeddings()  # Only computes 100 new embeddings
```

### 2D Projections

After computing embeddings, generate 2D projections:

```python
dataset.compute_visualization()
```

This creates:

1. **Euclidean projection**: Standard UMAP projection to 2D
2. **Hyperbolic projection**: Projection to Poincaré disk

**Note:** Projections are recomputed when new samples are added because UMAP requires refitting on the entire dataset.

## Managing Datasets

### List All Datasets

```python
# Get list of all persistent datasets
datasets = hv.Dataset.list_datasets()
print(datasets)  # ['cifar100_demo', 'my_dataset', 'medical_images']
```

### Check Existence

```python
if hv.Dataset.exists("my_dataset"):
    print("Dataset exists!")
    dataset = hv.Dataset("my_dataset")
else:
    print("Creating new dataset...")
    dataset = hv.Dataset("my_dataset")
    # Add samples...
```

### Delete a Dataset

```python
# Permanently delete a dataset
hv.Dataset.delete("old_dataset")
```

### Save and Load

#### Save to File

```python
# Save dataset to a JSON file
dataset.save("my_dataset_backup.json")
```

This saves:
- Dataset name and metadata
- All samples with their IDs and labels
- Embeddings (if computed)
- 2D projection coordinates (if computed)

#### Load from File

```python
# Load dataset from JSON file
dataset = hv.Dataset.load("my_dataset_backup.json")

# Continue working
hv.launch(dataset)
```

## Dataset Information

### Basic Info

```python
# Number of samples
print(f"Samples: {len(dataset)}")

# Dataset name
print(f"Name: {dataset.name}")

# Unique labels
print(f"Labels: {dataset.labels}")
```

### Iterate Over Samples

```python
# Iterate over all samples
for sample in dataset.samples:
    print(f"ID: {sample.id}")
    print(f"Label: {sample.label}")
    print(f"Has embedding: {sample.embedding is not None}")
```

### Access Individual Samples

```python
# Get sample by ID
sample = dataset[sample_id]

print(sample.id)
print(sample.label)
print(sample.image)  # PIL Image
print(sample.embedding)  # numpy array or None
```

## Best Practices

### 1. Start Small, Scale Up

```python
# Test with a small subset first
dataset = hv.Dataset("test")
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=100)
dataset.compute_embeddings()
dataset.compute_visualization()
hv.launch(dataset)

# If it works, scale up
dataset.add_from_huggingface("uoft-cs/cifar100", max_samples=5000)
dataset.compute_embeddings()
dataset.compute_visualization()
```

### 2. Save Checkpoints

```python
# Save after major steps
dataset.compute_embeddings()
dataset.save("checkpoint_embeddings.json")

dataset.compute_visualization()
dataset.save("checkpoint_complete.json")
```

### 3. Use Persistent Datasets for Large Projects

```python
# For large datasets, use persistent storage
dataset = hv.Dataset("large_project", persist=True)

# Work over multiple sessions
# Session 1: Add samples
# Session 2: Compute embeddings
# Session 3: Visualize
```

### 4. Clean Up Unused Datasets

```python
# List all datasets
all_datasets = hv.Dataset.list_datasets()
print(f"Found {len(all_datasets)} datasets")

# Delete old datasets
for name in all_datasets:
    if "temp" in name or "test" in name:
        hv.Dataset.delete(name)
        print(f"Deleted {name}")
```

## Next Steps

- [Computing Embeddings](embeddings.md) - Learn about different embedding models
- [Visualization Guide](visualization.md) - Customize your visualizations
- [Understanding Hyperbolic Space](../concepts/hyperbolic.md) - Why it matters
