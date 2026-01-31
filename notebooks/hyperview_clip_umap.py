# %% [markdown]
# # HyperView Demo: Image Embeddings + UMAP Visualization
#
# Demonstrates computing image embeddings and visualizing them in 2D using UMAP
# with the HyperView Dataset API. Supports CLIP and SigLip models.

# %%
import json
import random
import urllib.parse
import urllib.request
from pathlib import Path

import hyperview as hv

# %% [markdown]
# ## Download Random Space Images (NASA, Public Domain)
#
# This demo downloads a random set of space images from NASA's Images and Video Library
# (https://images.nasa.gov). NASA imagery is generally public domain (US Government work).

# %%
NUM_IMAGES = 48
CACHE_DIR = Path(__file__).parent / "_nasa_space_images"
RANDOM_SEED = None  # Set to an int (e.g. 0) for reproducible sampling
NASA_QUERIES = ["black hole", "nebula", "galaxy", "jwst", "hubble"]


CACHE_DIR.mkdir(parents=True, exist_ok=True)
image_files = [
    p
    for p in CACHE_DIR.iterdir()
    if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
]
if len(image_files) < NUM_IMAGES:
    rng = random.Random(RANDOM_SEED)
    query = rng.choice(NASA_QUERIES)
    params = {"q": query, "media_type": "image", "page": "1"}
    api_url = f"https://images-api.nasa.gov/search?{urllib.parse.urlencode(params)}"
    items = json.load(urllib.request.urlopen(api_url))["collection"]["items"]
    rng.shuffle(items)

    for i, item in enumerate(items[:NUM_IMAGES]):
        href = item["links"][0]["href"]
        ext = Path(urllib.parse.urlparse(href).path).suffix or ".jpg"
        urllib.request.urlretrieve(href, CACHE_DIR / f"nasa_{i:03d}{ext}")

dataset = hv.Dataset("nasa_space_demo", persist=False)
added, skipped = dataset.add_images_dir(str(CACHE_DIR), label_from_folder=False)
print(f"✓ Loaded {added} NASA space images" + (f" ({skipped} already present)" if skipped else ""))

# %% [markdown]
# ## Compute Embeddings & UMAP Projection
#
# EmbedAnything supports many HuggingFace vision models, but not all.
# For example, `microsoft/resnet-18` is currently rejected by EmbedAnything
# ("Model not supported"). Common choices that work:
# - CLIP: openai/clip-vit-base-patch32, openai/clip-vit-base-patch16, etc.
# - SigLip: google/siglip-base-patch16-224, google/siglip-large-patch16-384
# - Jina CLIP: jinaai/jina-clip-v2

# %%
# Use any HuggingFace model supported by EmbedAnything
MODEL = "google/siglip-base-patch16-224"

dataset.compute_embeddings(model=MODEL, show_progress=True)
dataset.compute_visualization()

# %% [markdown]
# ## Launch HyperView

# %%
hv.launch(dataset, port=6262, open_browser=True)


