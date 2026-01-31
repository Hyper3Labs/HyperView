# Running HyperView in Google Colab

HyperView works natively in Google Colab. Because Colab runs on a remote VM, you cannot access `localhost` directly. HyperView handles this automatically.

## Usage

### 1. Install HyperView

```bash
!pip install -q git+https://github.com/Hyper3Labs/HyperView.git
```

### 2. Launch the visualizer

When you run `hv.launch()`, a button labeled **“Open HyperView in a new tab”** will appear in the output. Click it to open the visualization.

```python
# Minimal example
import numpy as np
import hyperview as hv
from hyperview.core.sample import SampleFromArray

dataset = hv.Dataset("colab_smoke", persist=False)

rng = np.random.default_rng(0)
for i in range(200):
    img = (rng.random((64, 64, 3)) * 255).astype(np.uint8)
    sample = SampleFromArray.from_array(id=f"s{i}", image_array=img, label="demo")
    sample.embedding_2d = [float(rng.normal()), float(rng.normal())] # Dummy 2D points
    dataset.add_sample(sample)

hv.launch(dataset)
```

## Technical Details

To support Colab, HyperView uses `google.colab.kernel.proxyPort` to expose the backend server. The UI is opened via a specially constructed "launcher" page that embeds the proxied application in a full-page iframe. This workaround ensures compatibility with modern browser security policies (like third-party cookie blocking) that often break direct proxy URLs.
