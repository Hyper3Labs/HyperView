"""Demo: multimodal image+text retrieval with CLIP embeddings."""

from __future__ import annotations

import hyperview as hv

DATASET_NAME = "coco_captions_demo"
WORKSPACE_NAME = "coco_captions_demo"

dataset = hv.Dataset(DATASET_NAME)

added, skipped = dataset.add_from_huggingface(
    "HuggingFaceM4/COCO",
    split="train",
    max_samples=200,
    image_key="image",
    text_key="sentences",
    label_key=None,
)
print(f"Ingested {added} samples ({skipped} skipped)")

space_key = dataset.compute_embeddings(model="openai/clip-vit-base-patch32")
layout_key = dataset.compute_visualization(method="umap", layout_dimension=2)
print(f"Embeddings: {space_key}")
print(f"Layout: {layout_key}")

session = hv.launch(dataset, workspace_id=WORKSPACE_NAME, block=False)
results = session.ui.query_by_text("a dog playing in the park", k=10)
print(f"Top text-query matches: {[sample.id for sample, _distance in results]}")
session.wait()
