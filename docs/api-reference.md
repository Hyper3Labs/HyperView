# API Reference

Complete API reference for HyperView.

> **Note**: For detailed usage examples, see the [Python API Guide](getting-started/api.md).

## Module: `hyperview`

### Classes

#### `Dataset`

Main class for dataset management.

```python
class Dataset:
    """A collection of samples with embeddings and visualizations."""
```

**Constructor:**

```python
Dataset(name: str, persist: bool = True)
```

**Parameters:**
- `name` (str): Dataset identifier
- `persist` (bool): Store to disk (default: True)

**Methods:**

##### `add_from_huggingface()`

```python
def add_from_huggingface(
    self,
    dataset_id: str,
    split: str = "train",
    image_key: str = "img",
    label_key: str = "label",
    max_samples: Optional[int] = None
) -> None
```

Load samples from HuggingFace Hub.

##### `add_images_dir()`

```python
def add_images_dir(
    self,
    path: str,
    label_from_folder: bool = False
) -> None
```

Load images from local directory.

##### `compute_embeddings()`

```python
def compute_embeddings(
    self,
    model: str = "clip",
    show_progress: bool = True
) -> None
```

Compute high-dimensional embeddings.

##### `compute_visualization()`

```python
def compute_visualization(self) -> None
```

Generate 2D projections (Euclidean + Hyperbolic).

##### `save()`

```python
def save(self, filepath: str) -> None
```

Save dataset to file.

##### `load()` (classmethod)

```python
@classmethod
def load(cls, filepath: str) -> "Dataset"
```

Load dataset from file.

##### `list_datasets()` (classmethod)

```python
@classmethod
def list_datasets(cls) -> List[str]
```

List all persistent datasets.

##### `delete()` (classmethod)

```python
@classmethod
def delete(cls, name: str) -> None
```

Delete a persistent dataset.

##### `exists()` (classmethod)

```python
@classmethod
def exists(cls, name: str) -> bool
```

Check if dataset exists.

**Properties:**

- `name` (str): Dataset name
- `labels` (List[str]): Unique labels
- `samples` (Iterator[Sample]): Sample iterator

**Special Methods:**

- `__len__()`: Number of samples
- `__getitem__(sample_id)`: Get sample by ID

---

#### `Sample`

Represents a single data sample.

```python
class Sample:
    """A single sample with image, label, and embeddings."""
    
    id: str
    label: str
    image: PIL.Image
    embedding: Optional[np.ndarray]
    euclidean_coords: Optional[Tuple[float, float]]
    hyperbolic_coords: Optional[Tuple[float, float]]
```

---

### Functions

#### `launch()`

```python
def launch(
    dataset: Dataset,
    port: int = 5151,
    host: str = "127.0.0.1",
    open_browser: bool = True
) -> None
```

Start the HyperView web interface.

**Parameters:**
- `dataset`: Dataset to visualize
- `port`: Server port (default: 5151)
- `host`: Host address (default: "127.0.0.1")
- `open_browser`: Auto-open browser (default: True)

---

## REST API

When the server is running via `launch()`, these endpoints are available:

### `GET /api/dataset`

Get dataset metadata.

**Response:**
```json
{
  "name": "string",
  "total_samples": 1000,
  "labels": ["label1", "label2", ...],
  "colors": {
    "label1": "#color1",
    "label2": "#color2"
  }
}
```

### `GET /api/samples`

Get paginated samples with thumbnails.

**Query Parameters:**
- `page` (int): Page number (default: 1)
- `per_page` (int): Samples per page (default: 50)

**Response:**
```json
{
  "samples": [
    {
      "id": "sample_001",
      "label": "cat",
      "thumbnail": "data:image/jpeg;base64,..."
    },
    ...
  ],
  "total": 1000,
  "page": 1,
  "per_page": 50,
  "total_pages": 20
}
```

### `GET /api/embeddings`

Get 2D coordinates for all samples.

**Response:**
```json
{
  "euclidean": [
    {
      "id": "sample_001",
      "x": 0.5,
      "y": -0.3,
      "label": "cat"
    },
    ...
  ],
  "hyperbolic": [
    {
      "id": "sample_001",
      "x": 0.85,
      "y": 0.2,
      "label": "cat"
    },
    ...
  ]
}
```

### `POST /api/selection`

Sync selection state.

**Request:**
```json
{
  "selected_ids": ["sample_001", "sample_002", ...]
}
```

**Response:**
```json
{
  "status": "ok",
  "count": 2
}
```

### `GET /api/sample/{id}/image`

Get full-resolution image for a sample.

**Response:** Image binary data (JPEG/PNG)

---

## CLI

Command-line interface for HyperView.

### `hyperview demo`

Run the demo with CIFAR-100.

```bash
hyperview demo [OPTIONS]
```

**Options:**
- `--samples N`: Number of samples (default: 500)
- `--port PORT`: Server port (default: 5151)
- `--no-browser`: Don't auto-open browser

**Examples:**
```bash
# Run with 1000 samples
hyperview demo --samples 1000

# Use custom port
hyperview demo --port 8080

# Don't open browser
hyperview demo --no-browser
```

---

## Environment Variables

### `HYPERVIEW_DATABASE_DIR`

Override default database location.

```bash
export HYPERVIEW_DATABASE_DIR=/path/to/storage
```

Default: `~/.hyperview/lancedb/`

---

## Type Definitions

### `EmbeddingModel`

```python
EmbeddingModel = Literal["clip"]
```

Currently supported: `"clip"`

### `ViewMode`

```python
ViewMode = Literal["euclidean", "hyperbolic"]
```

Visualization modes.

### `Coordinates`

```python
Coordinates = Tuple[float, float]
```

2D coordinates (x, y).

---

## Exceptions

### `DatasetNotFoundError`

Raised when dataset doesn't exist.

```python
try:
    dataset = hv.Dataset.load("nonexistent.json")
except hv.DatasetNotFoundError:
    print("Dataset not found!")
```

### `EmbeddingsNotComputedError`

Raised when trying to visualize without embeddings.

```python
try:
    dataset.compute_visualization()
except hv.EmbeddingsNotComputedError:
    print("Compute embeddings first!")
    dataset.compute_embeddings()
```

---

## Constants

### `DEFAULT_PORT`

Default server port: `5151`

### `DEFAULT_HOST`

Default host: `"127.0.0.1"`

### `DEFAULT_MODEL`

Default embedding model: `"clip"`

---

## Version

```python
import hyperview as hv
print(hv.__version__)  # "0.1.0"
```

---

## Next Steps

- [Python API Guide](getting-started/api.md) - Usage examples
- [Working with Datasets](guide/datasets.md) - Dataset operations
- [Computing Embeddings](guide/embeddings.md) - Embedding details
