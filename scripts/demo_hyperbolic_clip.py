#!/usr/bin/env python
"""Demo: CLIP (Euclidean) + HyCoCLIP (Poincaré) on Imagenette."""

import hyperview as hv

DATASET_NAME = "imagenette_val_clip_hycoclip_demo"
HF_DATASET = "Multimodal-Fatima/Imagenette_validation"
HF_SPLIT = "validation"
HF_IMAGE_KEY = "image"
HF_LABEL_KEY = "label"
NUM_SAMPLES = 300
CLIP_MODEL_ID = "openai/clip-vit-base-patch32"
HYPER_MODELS_MODEL_ID = "hycoclip-vit-s"


def main() -> None:
    print("Loading Imagenette validation from Hugging Face...")
    dataset = hv.Dataset(DATASET_NAME, persist=False)
    dataset.add_from_huggingface(
        HF_DATASET,
        split=HF_SPLIT,
        image_key=HF_IMAGE_KEY,
        label_key=HF_LABEL_KEY,
        max_samples=NUM_SAMPLES,
        shuffle=True,
    )
    print(f"Loaded {len(dataset)} samples")

    clip_space = dataset.compute_embeddings(CLIP_MODEL_ID)
    dataset.compute_visualization(space_key=clip_space, layout="euclidean")
    hyper_space = dataset.compute_embeddings(model=HYPER_MODELS_MODEL_ID)
    dataset.compute_visualization(space_key=hyper_space, layout="poincare")

    print("Launching at http://127.0.0.1:6262")

    hv.launch(dataset, open_browser=True)


if __name__ == "__main__":
    main()
