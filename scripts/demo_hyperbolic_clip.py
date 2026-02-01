#!/usr/bin/env python
"""Demo: CLIP (Euclidean) + hyper-models (Poincaré) on CIFAR-100."""

import hyperview as hv

DATASET_NAME = "cifar100_coarse_clip_hyper_models"
HF_DATASET = "uoft-cs/cifar100"
HF_SPLIT = "test"
HF_IMAGE_KEY = "img"
# NOTE: HyperView disables distinct label coloring when there are >20 labels.
# CIFAR-100 has 100 fine labels, but only 20 coarse labels.
HF_LABEL_KEY = "coarse_label"
NUM_SAMPLES = 200
CLIP_MODEL_ID = "openai/clip-vit-base-patch32"
HYPER_MODELS_MODEL_ID = "hycoclip-vit-s"


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
    hyper_space = dataset.compute_embeddings(model=HYPER_MODELS_MODEL_ID)
    dataset.compute_visualization(space_key=hyper_space, geometry="poincare")

    print("Launching at http://127.0.0.1:6262")

    hv.launch(dataset, open_browser=True)


if __name__ == "__main__":
    main()
