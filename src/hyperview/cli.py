"""Command-line interface for HyperView."""

from __future__ import annotations

import argparse

from hyperview import Dataset, launch
from hyperview.core.dataset import parse_visualization_layout


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hyperview",
        description="HyperView - Dataset visualization with hyperbolic embeddings",
    )

    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help=(
            "Dataset name in persistent storage. Required unless "
            "--dataset-json is provided."
        ),
    )
    parser.add_argument(
        "--dataset-json",
        type=str,
        help="Path to exported dataset JSON file (loads samples into memory)",
    )
    parser.add_argument(
        "--hf-dataset",
        type=str,
        help="HuggingFace dataset ID to ingest before launch (e.g. uoft-cs/cifar10)",
    )
    parser.add_argument(
        "--split",
        type=str,
        default=None,
        help="HuggingFace split to use (required with --hf-dataset)",
    )
    parser.add_argument(
        "--hf-config",
        type=str,
        default=None,
        help="Optional HuggingFace subset/configuration to use",
    )
    parser.add_argument(
        "--image-key",
        type=str,
        default=None,
        help="Image column key for HuggingFace ingestion (required with --hf-dataset)",
    )
    parser.add_argument(
        "--label-key",
        type=str,
        default=None,
        help="Label column key for HuggingFace ingestion (optional)",
    )
    parser.add_argument(
        "--label-names-key",
        type=str,
        default=None,
        help="Optional dataset info key containing label names",
    )
    parser.add_argument(
        "--images-dir",
        type=str,
        help="Local directory of images to ingest before launch",
    )
    parser.add_argument(
        "--label-from-folder",
        action="store_true",
        help="When using --images-dir, derive label from parent folder name",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=None,
        help="Maximum number of ingested samples (omit to load all)",
    )
    parser.add_argument(
        "--hf-streaming",
        action="store_true",
        help=(
            "Stream HuggingFace rows instead of materializing the full split first. "
            "Useful for loading subsets without eager full-split downloads."
        ),
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Shuffle HuggingFace dataset before sampling",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed used when --shuffle is enabled (default: 42)",
    )
    parser.add_argument(
        "--hf-shuffle-buffer-size",
        type=int,
        default=1000,
        help=(
            "Shuffle buffer size used with --hf-streaming and --shuffle. "
            "Streaming shuffle is approximate and trades larger buffers for more read-ahead."
        ),
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "Embedding model to compute before launch (e.g. openai/clip-vit-base-patch32). "
            "If omitted, existing embedding spaces are reused."
        ),
    )
    parser.add_argument(
        "--method",
        choices=["umap", "pca"],
        default="umap",
        help="Projection method: 'umap' (default) or 'pca'",
    )
    parser.add_argument(
        "--layout",
        action="append",
        dest="layouts",
        metavar="GEOMETRY[:2d|3d]",
        help=(
            "Visualization layout to compute. Repeat this flag to request multiple layouts, "
            "for example '--layout euclidean --layout spherical'. "
            "Omitting the suffix defaults to 2D for euclidean/poincare and 3D for spherical. "
            "If omitted, HyperView picks one sensible default layout for the selected embedding space."
        ),
    )
    parser.add_argument(
        "--n-neighbors",
        type=int,
        default=15,
        help="UMAP n_neighbors (default: 15)",
    )
    parser.add_argument(
        "--min-dist",
        type=float,
        default=0.1,
        help="UMAP min_dist (default: 0.1)",
    )
    parser.add_argument(
        "--metric",
        type=str,
        default="cosine",
        help="UMAP metric (default: cosine)",
    )
    parser.add_argument(
        "--force-layout",
        action="store_true",
        help="Force layout recomputation even if projection already exists",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=6262,
        help="Port to run the server on (default: 6262)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser window automatically",
    )
    parser.add_argument(
        "--reuse-server",
        action="store_true",
        help=(
            "If the port is already serving HyperView, attach instead of failing. "
            "For safety, this only attaches when the existing server reports the same dataset name."
        ),
    )

    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.layouts:
        canonical_layouts: list[str] = []
        seen_layouts: set[str] = set()
        for layout_spec in args.layouts:
            try:
                geometry, layout_dimension = parse_visualization_layout(layout_spec)
            except ValueError as exc:
                parser.error(str(exc))

            canonical_layout = f"{geometry}:{layout_dimension}d"
            if canonical_layout in seen_layouts:
                continue
            seen_layouts.add(canonical_layout)
            canonical_layouts.append(canonical_layout)

        args.layouts = canonical_layouts

    if args.hf_dataset and args.images_dir:
        parser.error("Use either --hf-dataset or --images-dir, not both.")

    if args.dataset_json and (args.hf_dataset or args.images_dir):
        parser.error("--dataset-json cannot be combined with --hf-dataset or --images-dir.")

    if args.dataset_json and args.dataset:
        parser.error("Use either --dataset or --dataset-json, not both.")

    if not args.dataset and not args.dataset_json:
        parser.error(
            "Provide --dataset (persistent dataset) or --dataset-json (exported dataset file)."
        )

    if args.hf_dataset:
        if not args.split:
            parser.error("--split is required when using --hf-dataset.")
        if not args.image_key:
            parser.error("--image-key is required when using --hf-dataset.")
        if args.hf_shuffle_buffer_size < 1:
            parser.error("--hf-shuffle-buffer-size must be at least 1.")


def _print_ingestion_result(added: int, skipped: int) -> None:
    if skipped > 0:
        print(f"Loaded {added} samples ({skipped} already present)")
    else:
        print(f"Loaded {added} samples")


def _ingest_huggingface(dataset: Dataset, args: argparse.Namespace, dataset_name: str) -> None:
    config_suffix = f" [{args.hf_config}]" if args.hf_config else ""
    print(f"Loading HuggingFace dataset {dataset_name}{config_suffix}...")
    added, skipped = dataset.add_from_huggingface(
        dataset_name,
        config=args.hf_config,
        split=args.split,
        image_key=args.image_key,
        label_key=args.label_key,
        label_names_key=args.label_names_key,
        max_samples=args.samples,
        shuffle=args.shuffle,
        seed=args.seed,
        streaming=args.hf_streaming,
        shuffle_buffer_size=args.hf_shuffle_buffer_size,
    )
    _print_ingestion_result(added, skipped)


def _prepare_dataset(args: argparse.Namespace) -> Dataset:
    if args.dataset_json:
        print(f"Loading dataset from {args.dataset_json}...")
        dataset = Dataset.load(args.dataset_json)
        print(f"Loaded {len(dataset)} samples")
        return dataset

    dataset = Dataset(args.dataset)
    print(f"Using dataset '{dataset.name}' ({len(dataset)} samples)")

    if args.hf_dataset:
        _ingest_huggingface(dataset, args, args.hf_dataset)
    elif args.images_dir:
        print(f"Loading images from {args.images_dir}...")
        added, skipped = dataset.add_images_dir(
            args.images_dir,
            label_from_folder=args.label_from_folder,
        )
        _print_ingestion_result(added, skipped)

    return dataset


def _resolve_default_layouts(
    dataset: Dataset,
    space_key: str | None,
) -> list[str]:
    spaces = dataset.list_spaces()
    selected = next((space for space in spaces if space.space_key == space_key), None)

    if selected is not None:
        if selected.geometry == "hyperboloid":
            return ["poincare:2d"]
        if selected.geometry == "hypersphere":
            return ["spherical:3d"]
        return ["euclidean:2d"]

    if any(space.geometry not in ("hyperboloid", "hypersphere") for space in spaces):
        return ["euclidean:2d"]
    if any(space.geometry == "hypersphere" for space in spaces):
        return ["spherical:3d"]
    return ["poincare:2d"]

def _compute_layouts(dataset: Dataset, args: argparse.Namespace, space_key: str | None) -> None:
    target_layouts = args.layouts or _resolve_default_layouts(dataset, space_key)

    print("Computing visualizations...")
    for target_layout in target_layouts:
        dataset.compute_visualization(
            space_key=space_key,
            method=args.method,
            layout=target_layout,
            n_neighbors=args.n_neighbors,
            min_dist=args.min_dist,
            metric=args.metric,
            force=args.force_layout,
        )
    print("Visualizations ready")


def _prepare_embeddings_and_layouts(dataset: Dataset, args: argparse.Namespace) -> None:
    has_spaces = len(dataset.list_spaces()) > 0

    if args.model is not None:
        print(f"Computing embeddings with {args.model}...")
        space_key = dataset.compute_embeddings(model=args.model, show_progress=True)
        print("Embeddings computed")
        _compute_layouts(dataset, args, space_key)
        return

    if args.force_layout:
        if not has_spaces:
            raise ValueError(
                "No embedding spaces found. Provide --model to compute embeddings first."
            )
        _compute_layouts(dataset, args, space_key=None)
        return

    if not has_spaces:
        raise ValueError(
            "No embedding spaces found. Provide --model to compute embeddings first."
        )


def main():
    """Main CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    _validate_args(parser, args)

    dataset = _prepare_dataset(args)
    _prepare_embeddings_and_layouts(dataset, args)

    launch(
        dataset,
        port=args.port,
        host=args.host,
        open_browser=not args.no_browser,
        reuse_server=args.reuse_server,
    )


if __name__ == "__main__":
    main()
