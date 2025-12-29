# Python API

This page provides a comprehensive overview of HyperView's Python API.

## Core Classes

### Dataset

The main class for working with datasets in HyperView.

```python
import hyperview as hv

# Create a new dataset
dataset = hv.Dataset("my_dataset")

# Create in-memory dataset (not persisted)
dataset = hv.Dataset("temp_dataset", persist=False)
```

#### Constructor

```python
Dataset(name: str, persist: bool = True)
```

**Parameters:**

- `name` (str): Name of the dataset
- `persist` (bool): Whether to persist to disk (default: True)

**Storage Location:** `~/.hyperview/lancedb/` (configurable via `HYPERVIEW_DATABASE_DIR`)

### Methods

#### add_from_huggingface()

Load samples from HuggingFace Hub.

```python
dataset.add_from_huggingface(
    dataset_id="uoft-cs/cifar100",
    split="train",
    image_key="img",
    label_key="fine_label",
    max_samples=1000
)
```

**Parameters:**

- `dataset_id` (str): HuggingFace dataset identifier
- `split` (str): Dataset split (e.g., "train", "test")
- `image_key` (str): Key for image column (default: "img")
- `label_key` (str): Key for label column (default: "label")
- `max_samples` (int, optional): Maximum number of samples to load

#### add_images_dir()

Load images from a local directory.

```python
dataset.add_images_dir(
    path="/path/to/images",
    label_from_folder=True
)
```

**Parameters:**

- `path` (str): Path to image directory
- `label_from_folder` (bool): Use folder names as labels (default: False)

**Expected Structure (when `label_from_folder=True`):**
```
/path/to/images/
├── cat/
│   ├── img1.jpg
│   └── img2.jpg
└── dog/
    ├── img1.jpg
    └── img2.jpg
```

#### compute_embeddings()

Compute high-dimensional embeddings for all samples.

```python
dataset.compute_embeddings(
    model="clip",
    show_progress=True
)
```

**Parameters:**

- `model` (str): Embedding model to use (default: "clip")
- `show_progress` (bool): Show progress bar (default: True)

**Supported Models:**

- `"clip"`: CLIP embeddings (default)
- Additional models may be available through EmbedAnything

**Note:** Embeddings are cached per-sample. If a sample already has embeddings, it will be skipped.

#### compute_visualization()

Generate 2D projections for visualization.

```python
dataset.compute_visualization()
```

This computes:

- **Euclidean projection**: UMAP projection to 2D Euclidean space
- **Hyperbolic projection**: Projection to Poincaré disk

**Note:** This method must be called after `compute_embeddings()`.

#### save()

Save the dataset to disk.

```python
dataset.save("my_dataset.json")
```

**Parameters:**

- `filepath` (str): Path to save the dataset

**What's Saved:**

- Dataset metadata
- Sample information
- Embeddings (if computed)
- Visualization coordinates

#### load() (Class Method)

Load a previously saved dataset.

```python
dataset = hv.Dataset.load("my_dataset.json")
```

**Parameters:**

- `filepath` (str): Path to saved dataset file

**Returns:** Dataset instance

#### list_datasets() (Class Method)

List all persistent datasets.

```python
datasets = hv.Dataset.list_datasets()
print(datasets)  # ['cifar100_demo', 'my_dataset', ...]
```

**Returns:** List of dataset names

#### delete() (Class Method)

Delete a persistent dataset.

```python
hv.Dataset.delete("my_dataset")
```

**Parameters:**

- `name` (str): Name of dataset to delete

**Warning:** This permanently deletes the dataset and all associated data.

#### exists() (Class Method)

Check if a dataset exists.

```python
if hv.Dataset.exists("my_dataset"):
    print("Dataset exists!")
```

**Parameters:**

- `name` (str): Dataset name to check

**Returns:** Boolean

### Properties

```python
# Number of samples
print(len(dataset))

# Dataset name
print(dataset.name)

# Unique labels
print(dataset.labels)

# Iterate over samples
for sample in dataset.samples:
    print(sample.id, sample.label)

# Get sample by ID
sample = dataset[sample_id]
```

## Launch Function

### launch()

Start the HyperView web interface.

```python
hv.launch(
    dataset,
    port=5151,
    open_browser=True,
    host="127.0.0.1"
)
```

**Parameters:**

- `dataset` (Dataset): Dataset to visualize
- `port` (int): Server port (default: 5151)
- `open_browser` (bool): Automatically open browser (default: True)
- `host` (str): Host address (default: "127.0.0.1")

**Example:**

```python
import hyperview as hv

dataset = hv.Dataset.load("my_dataset.json")
hv.launch(dataset, port=8080)
```

## API Endpoints

When the server is running, these REST endpoints are available:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dataset` | GET | Dataset metadata (name, labels, colors) |
| `/api/samples` | GET | Paginated samples with thumbnails |
| `/api/embeddings` | GET | 2D coordinates (Euclidean + Hyperbolic) |
| `/api/selection` | POST | Sync selection state |

## Complete Workflow Example

```python
import hyperview as hv

# 1. Create dataset
dataset = hv.Dataset("medical_images")

# 2. Load data
dataset.add_images_dir(
    "/data/xrays",
    label_from_folder=True
)

# 3. Compute embeddings
dataset.compute_embeddings(
    model="clip",
    show_progress=True
)

# 4. Generate visualizations
dataset.compute_visualization()

# 5. Save for later
dataset.save("medical_images.json")

# 6. Launch UI
hv.launch(dataset)

# Later: Load and explore
dataset = hv.Dataset.load("medical_images.json")
hv.launch(dataset)
```

## Next Steps

- [Working with Datasets](../guide/datasets.md) - Detailed dataset operations
- [Computing Embeddings](../guide/embeddings.md) - Advanced embedding options
- [Architecture Overview](../concepts/architecture.md) - How it all works
