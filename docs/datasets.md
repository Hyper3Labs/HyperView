# Datasets

## Creating a Dataset

```python
import hyperview as hv

# Persistent dataset (default) - survives restarts
dataset = hv.Dataset("my_dataset")

# In-memory dataset - lost when process exits
dataset = hv.Dataset("my_dataset", persist=False)
```

**Storage location:** `~/.hyperview/datasets/` (configurable via `HYPERVIEW_DATABASE_DIR`)

Internally, each dataset is stored as two Lance tables (directories) inside that folder:
- `hyperview_{dataset_name}.lance/` (samples)
- `hyperview_{dataset_name}_meta.lance/` (metadata like label colors)

## Adding Samples

### From HuggingFace
```python
dataset.add_from_huggingface(
    "uoft-cs/cifar100",
    split="train",
    image_key="img",
    label_key="fine_label",
    max_samples=1000,
)
```

To target a named Hugging Face subset/configuration, pass `config="default"`
or another config name alongside `split=`.

To avoid materializing the full split before sampling, use `streaming=True`.
This keeps ingestion on Hugging Face's iterable dataset path and stops after the
requested rows:

```python
dataset.add_from_huggingface(
    "uoft-cs/cifar100",
    split="train",
    image_key="img",
    label_key="fine_label",
    max_samples=500,
    streaming=True,
)
```

When `streaming=True` and `shuffle=True`, sampling becomes approximate and
buffer-based. Tune `shuffle_buffer_size=` if you need more mixing and can afford
additional read-ahead.

### From Directory
```python
dataset.add_images_dir("/path/to/images", label_from_folder=True)
```

## Persistence Model: Additive

HyperView uses an **additive** persistence model:

| Action | Behavior |
|--------|----------|
| Add samples | New samples inserted, existing skipped by ID |
| Request fewer than exist | Existing samples preserved (no deletion) |
| Request more than exist | Only new samples added |
| Embeddings | Cached per-sample, reused across sessions |
| Projections | Recomputed when new samples added (UMAP requires refit) |

**Example:**
```python
dataset = hv.Dataset("my_dataset")

dataset.add_from_huggingface(..., max_samples=200)  # 200 samples
dataset.add_from_huggingface(..., max_samples=400)  # +200 new → 400 total
dataset.add_from_huggingface(..., max_samples=300)  # no change → 400 total
dataset.add_from_huggingface(..., max_samples=500)  # +100 new → 500 total
```

Samples are **never implicitly deleted**. Use `hv.Dataset.delete("name")` for explicit removal.

## Computing Embeddings

```python
# High-dimensional embeddings (CLIP)
dataset.compute_embeddings(model="openai/clip-vit-base-patch32", show_progress=True)

# 2D projection for visualization
dataset.compute_visualization()  # Defaults to euclidean:2d
```

Embeddings are stored per-sample. If a sample already has embeddings, it's skipped.

## Listing & Deleting Datasets

```python
# List all persistent datasets
hv.Dataset.list_datasets()  # ['cifar100_demo', 'my_dataset', ...]

# Delete a dataset
hv.Dataset.delete("my_dataset")

# Check existence
hv.Dataset.exists("my_dataset")  # True/False
```

## Dataset Info

```python
len(dataset)           # Number of samples
dataset.name           # Dataset name
dataset.labels         # Unique labels
dataset.samples        # Iterator over all samples
dataset[sample_id]     # Get sample by ID
```
