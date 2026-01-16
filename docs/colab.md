# Running HyperView in Google Colab

Colab notebooks run on a remote VM, so you **can’t** open `http://127.0.0.1:<port>` directly from your local browser.

HyperView detects Colab and shows an **“Open HyperView in a new tab”** button that opens a same-site blank tab and embeds the proxied app URL in a full-page iframe (this avoids known issues with opening the proxied URL as a top-level page due to browser cookie partitioning).

## Quick smoke test (no model downloads)

This smoke test creates a tiny synthetic dataset with random images + precomputed 2D coordinates, so you can validate the UI and the “open in new tab” flow without running CLIP/UMAP.

### 1) Install HyperView

```bash
!pip install -q git+https://github.com/HackerRoomAI/HyperView.git
```

### 2) Create a synthetic dataset and launch

```python
import numpy as np
import hyperview as hv
from hyperview.core.sample import SampleFromArray

dataset = hv.Dataset("colab_smoke", persist=False)

rng = np.random.default_rng(0)
num_samples = 200

for i in range(num_samples):
    # Random 64x64 RGB image
    img = (rng.random((64, 64, 3)) * 255).astype(np.uint8)

    sample = SampleFromArray.from_array(
        id=f"s{i}",
        image_array=img,
        label=f"class_{i % 10}",
        metadata={"i": i},
    )

    # Precomputed 2D Euclidean projection
    sample.embedding_2d = [float(rng.normal()), float(rng.normal())]

    # Precomputed 2D hyperbolic projection (inside unit disk)
    r = float(rng.random() * 0.95)
    theta = float(rng.random() * 2 * np.pi)
    sample.embedding_2d_hyperbolic = [float(r * np.cos(theta)), float(r * np.sin(theta))]

    dataset.add_sample(sample)

hv.launch(dataset, port=5151)
```

Click **“Open HyperView in a new tab”**.

If your browser blocks popups, HyperView will fall back to an inline iframe view inside the notebook output.

## Full demo (real embeddings)

If you want the full pipeline (download images, compute CLIP embeddings, run UMAP, etc.), use the demo flow described in the project README.
