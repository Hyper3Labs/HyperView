#!/usr/bin/env python
"""Demo: Jaguar Re-ID with MegaDescriptor in a spherical 3D view."""

import hyperview as hv

DATASET_NAME = "jaguar_reid_megadescriptor_spherical_demo"
MODEL_ID = "hf-hub:BVRA/MegaDescriptor-L-384"
SAMPLE_COUNT = 200


def main() -> None:
    dataset = hv.Dataset(DATASET_NAME, persist=False)

    dataset.add_from_huggingface(
        "hyper3labs/jaguar-re-id",
        image_key="image",
        label_key="label",
        max_samples=SAMPLE_COUNT,
    )

    space_key = dataset.compute_embeddings(
        model=MODEL_ID,
        provider="timm-image",
        batch_size=8,
    )

    dataset.compute_visualization(space_key=space_key, layout="spherical")
    dataset.compute_visualization(space_key=space_key, method="pca", layout="spherical")

    hv.launch(dataset)


if __name__ == "__main__":
    main()
