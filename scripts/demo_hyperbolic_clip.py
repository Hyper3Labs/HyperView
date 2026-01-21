#!/usr/bin/env python
"""Demo: CLIP (Euclidean) + HyCoCLIP (Poincaré) on CIFAR-100."""

import hyperview as hv
import hyperview.embeddings.providers.hycoclip  # noqa: F401
from hyperview.embeddings.providers import ModelSpec

DATASET_NAME = "cifar100_clip_hycoclip"
HF_DATASET = "uoft-cs/cifar100"
HF_SPLIT = "test"
HF_IMAGE_KEY = "img"
HF_LABEL_KEY = "fine_label"
NUM_SAMPLES = 200
CLIP_MODEL_ID = "openai/clip-vit-base-patch32"
HYCOCLIP_MODEL_ID = "hycoclip_vit_s"


def main() -> None:
    print("Loading CIFAR-100 from Hugging Face...")
    dataset = hv.Dataset(DATASET_NAME, persist=False)
    dataset.add_from_huggingface(
        HF_DATASET,
        split=HF_SPLIT,
        image_key=HF_IMAGE_KEY,
        label_key=HF_LABEL_KEY,
        max_samples=NUM_SAMPLES,
    )
    print(f"Loaded {len(dataset)} samples")

    clip_space = dataset.compute_embeddings(CLIP_MODEL_ID)
    dataset.compute_visualization(space_key=clip_space, geometry="euclidean")
    hycoclip_spec = ModelSpec(provider="hycoclip", model_id=HYCOCLIP_MODEL_ID)
    hycoclip_space = dataset.compute_embeddings(hycoclip_spec)
    dataset.compute_visualization(space_key=hycoclip_space, geometry="poincare")

    print("Launching at http://127.0.0.1:6262")

    hv.launch(dataset, open_browser=True)


if __name__ == "__main__":
    main()
