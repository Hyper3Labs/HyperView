#!/usr/bin/env python3
"""Run HyperView demo with CIFAR-100 dataset."""

import argparse
import os
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main():
    parser = argparse.ArgumentParser(description="Run HyperView demo")
    parser.add_argument(
        "--dataset",
        type=str,
        default="cifar100_demo",
        help="Dataset name to use for persistence (default: cifar100_demo)",
    )
    parser.add_argument(
        "--samples", type=int, default=50000, help="Number of samples to load (default: 50000)"
    )
    parser.add_argument(
        "--port", type=int, default=6262, help="Port to run server on (default: 6262)"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't open browser automatically"
    )
    parser.add_argument(
        "--no-persist", action="store_true", help="Don't persist to database (use in-memory)"
    )
    parser.add_argument(
        "--database-dir",
        type=str,
        default=None,
        help="Override persistence directory (sets HYPERVIEW_DATABASE_DIR)",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Don't start the web server (useful for CI / DB checks)",
    )
    args = parser.parse_args()

    if args.database_dir:
        os.environ["HYPERVIEW_DATABASE_DIR"] = args.database_dir

    import hyperview as hv

    dataset = hv.Dataset(args.dataset, persist=not args.no_persist)

    dataset.add_from_huggingface(
        "uoft-cs/cifar100",
        split="train",
        image_key="img",
        label_key="fine_label",
        max_samples=args.samples,
    )

    dataset.compute_embeddings(show_progress=True)

    dataset.compute_visualization()

    if args.no_server:
        return

    hv.launch(dataset, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
