"""Command-line interface for HyperView."""

import argparse
import sys

from hyperview import Dataset, launch


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="hyperview",
        description="HyperView - Dataset visualization with hyperbolic embeddings",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Demo command
    demo_parser = subparsers.add_parser("demo", help="Run a demo with sample data")
    demo_parser.add_argument(
        "--samples",
        type=int,
        default=500,
        help="Number of samples to load (default: 500)",
    )
    demo_parser.add_argument(
        "--port",
        type=int,
        default=6262,
        help="Port to run the server on (default: 6262)",
    )
    demo_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1)",
    )
    demo_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser window automatically",
    )
    demo_parser.add_argument(
        "--reuse-server",
        action="store_true",
        help=(
            "If the port is already serving HyperView, attach instead of failing. "
            "For safety, this only attaches when the existing server reports the same dataset name."
        ),
    )
    demo_parser.add_argument(
        "--model",
        type=str,
        default="openai/clip-vit-base-patch32",
        help="Embedding model to use (default: openai/clip-vit-base-patch32)",
    )

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Serve a saved dataset")
    serve_parser.add_argument("dataset", help="Path to saved dataset JSON file")
    serve_parser.add_argument(
        "--port",
        type=int,
        default=6262,
        help="Port to run the server on (default: 6262)",
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser window automatically",
    )
    serve_parser.add_argument(
        "--reuse-server",
        action="store_true",
        help=(
            "If the port is already serving HyperView, attach instead of failing. "
            "For safety, this only attaches when the existing server reports the same dataset name."
        ),
    )

    args = parser.parse_args()

    if args.command == "demo":
        run_demo(
            args.samples,
            args.port,
            host=args.host,
            open_browser=not args.no_browser,
            reuse_server=args.reuse_server,
            model=args.model,
        )
    elif args.command == "serve":
        serve_dataset(
            args.dataset,
            args.port,
            host=args.host,
            open_browser=not args.no_browser,
            reuse_server=args.reuse_server,
        )
    else:
        parser.print_help()
        sys.exit(1)


def run_demo(
    num_samples: int = 500,
    port: int = 6262,
    *,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    reuse_server: bool = False,
    model: str = "openai/clip-vit-base-patch32",
) -> None:
    """Run a demo with CIFAR-10 data."""
    print("Loading CIFAR-10 dataset...")
    dataset = Dataset("cifar10_demo")

    added, skipped = dataset.add_from_huggingface(
        "uoft-cs/cifar10",
        split="train",
        image_key="img",
        label_key="label",
        max_samples=num_samples,
    )
    if skipped > 0:
        print(f"Loaded {added} samples ({skipped} already present)")
    else:
        print(f"Loaded {added} samples")

    print(f"Computing embeddings with {model}...")
    space_key = dataset.compute_embeddings(model=model, show_progress=True)
    print("Embeddings computed")

    print("Computing visualizations...")
    # Compute both euclidean and poincare layouts
    dataset.compute_visualization(space_key=space_key, geometry="euclidean")
    dataset.compute_visualization(space_key=space_key, geometry="poincare")
    print("Visualizations ready")

    launch(dataset, port=port, host=host, open_browser=open_browser, reuse_server=reuse_server)


def serve_dataset(
    filepath: str,
    port: int = 6262,
    *,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    reuse_server: bool = False,
) -> None:
    """Serve a saved dataset."""
    from hyperview import Dataset, launch

    print(f"Loading dataset from {filepath}...")
    dataset = Dataset.load(filepath)
    print(f"Loaded {len(dataset)} samples")

    launch(dataset, port=port, host=host, open_browser=open_browser, reuse_server=reuse_server)


if __name__ == "__main__":
    main()
