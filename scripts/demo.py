#!/usr/bin/env python3
"""Run HyperView demo with CIFAR-10 dataset."""

import argparse
import os
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


DATASET_NAME = "cifar10_demo"
HF_DATASET = "uoft-cs/cifar10"
HF_SPLIT = "train"
HF_IMAGE_KEY = "img"
HF_LABEL_KEY = "label"
MODEL_ID = "openai/clip-vit-base-patch32"
DEFAULT_SAMPLE_COUNT = 500
DEFAULT_PORT = 6262


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HyperView demo")
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_SAMPLE_COUNT,
        help=f"Number of samples to load (default: {DEFAULT_SAMPLE_COUNT})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to run server on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't open browser automatically"
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help=(
            "Persist demo data to HyperView's database. "
            "The demo uses a sample-count-specific dataset name in DB mode."
        ),
    )
    parser.add_argument(
        "--datasets-dir",
        "--database-dir",
        type=str,
        default=None,
        help="Override the HyperView datasets directory when using --persist",
    )
    args = parser.parse_args()

    if args.samples < 1:
        parser.error("--samples must be at least 1")

    if args.datasets_dir:
        os.environ["HYPERVIEW_DATASETS_DIR"] = args.datasets_dir

    import hyperview as hv

    dataset_name = f"{DATASET_NAME}_{args.samples}" if args.persist else DATASET_NAME
    dataset = hv.Dataset(dataset_name, persist=args.persist)

    dataset.add_from_huggingface(
        HF_DATASET,
        split=HF_SPLIT,
        image_key=HF_IMAGE_KEY,
        label_key=HF_LABEL_KEY,
        max_samples=args.samples,
    )

    space_key = dataset.compute_embeddings(model=MODEL_ID, show_progress=True)

    # Compute the default hyperbolic 2D view plus a spherical view.
    # Bare "spherical" now resolves to the 3D spherical layout.
    dataset.compute_visualization(space_key=space_key, layout="euclidean:3d")
    dataset.compute_visualization(space_key=space_key, layout="poincare")
    dataset.compute_visualization(space_key=space_key, layout="spherical")

    hv.launch(dataset, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
