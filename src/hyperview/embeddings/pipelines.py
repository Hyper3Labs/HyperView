"""Compute orchestration pipelines for HyperView.

These functions coordinate embedding computation and 2D layout/projection
computation, persisting results into the configured storage backend.
"""

import numpy as np

from hyperview.storage.backend import StorageBackend
from hyperview.storage.schema import make_layout_key, make_space_key


def compute_missing_embeddings(
    storage: StorageBackend,
    model_id: str,
    batch_size: int = 32,
    show_progress: bool = True,
) -> tuple[str, int, int]:
    """Compute embeddings for samples that don't have them yet.

    Args:
        storage: Storage backend to read samples from and write embeddings to.
        model_id: EmbedAnything HuggingFace model_id to use.
        batch_size: Batch size for processing.
        show_progress: Whether to show progress bar.

    Returns:
        Tuple of (space_key, num_computed, num_skipped).

    Raises:
        ValueError: If no samples in storage.
    """
    from hyperview.embeddings.compute import EmbeddingComputer

    computer = EmbeddingComputer(model=model_id)

    all_samples = storage.get_all_samples()
    if not all_samples:
        raise ValueError("No samples in storage")

    test_embedding = computer.compute_single(all_samples[0])
    dim = len(test_embedding)

    space_key = make_space_key(model_id)
    provider_config = {
        "provider": "embed_anything",
        "geometry": "euclidean",
    }
    storage.ensure_space(model_id, dim, config=provider_config)

    missing_ids = storage.get_missing_embedding_ids(space_key)
    num_skipped = len(all_samples) - len(missing_ids)

    if not missing_ids:
        if show_progress:
            print(
                f"All {len(all_samples)} samples already have embeddings in space '{space_key}'"
            )
        return space_key, 0, num_skipped

    samples_needing_embeddings = storage.get_samples_by_ids(missing_ids)

    if show_progress and num_skipped > 0:
        print(f"Skipped {num_skipped} samples with existing embeddings")

    embeddings = computer.compute_batch(
        samples_needing_embeddings, batch_size=batch_size, show_progress=show_progress
    )

    ids = [s.id for s in samples_needing_embeddings]
    vectors = np.array(embeddings, dtype=np.float32)
    storage.add_embeddings(space_key, ids, vectors)

    return space_key, len(ids), num_skipped


def compute_layout(
    storage: StorageBackend,
    space_key: str | None = None,
    method: str = "umap",
    geometry: str = "euclidean",
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    metric: str = "cosine",
    force: bool = False,
    show_progress: bool = True,
) -> str:
    """Compute 2D layout/projection for visualization.

    Args:
        storage: Storage backend with embeddings.
        space_key: Embedding space to project. If None, uses the first available.
        method: Projection method ('umap' supported).
        geometry: Output geometry type ('euclidean' or 'poincare').
        n_neighbors: Number of neighbors for UMAP.
        min_dist: Minimum distance for UMAP.
        metric: Distance metric for UMAP.
        force: Force recomputation even if layout exists.
        show_progress: Whether to print progress messages.

    Returns:
        layout_key for the computed layout.

    Raises:
        ValueError: If no embedding spaces, space not found, or insufficient samples.
    """
    from hyperview.embeddings.projection import ProjectionEngine

    if method != "umap":
        raise ValueError(f"Invalid method: {method}. Only 'umap' is supported.")

    if geometry not in ("euclidean", "poincare"):
        raise ValueError(f"Invalid geometry: {geometry}. Must be 'euclidean' or 'poincare'.")

    if space_key is None:
        spaces = storage.list_spaces()
        if not spaces:
            raise ValueError("No embedding spaces. Call compute_embeddings() first.")
        space_key = spaces[0].space_key

    space = storage.get_space(space_key)
    if space is None:
        raise ValueError(f"Space not found: {space_key}")

    ids, vectors = storage.get_embeddings(space_key)
    if len(ids) == 0:
        raise ValueError(
            f"No embeddings in space '{space_key}'. Call compute_embeddings() first."
        )

    if len(ids) < 3:
        raise ValueError(f"Need at least 3 samples for visualization, have {len(ids)}")

    layout_params = {
        "n_neighbors": n_neighbors,
        "min_dist": min_dist,
        "metric": metric,
    }
    layout_key = make_layout_key(space_key, method, geometry, layout_params)

    if not force:
        existing_layout = storage.get_layout(layout_key)
        if existing_layout is not None:
            existing_ids, _ = storage.get_layout_coords(layout_key)
            if set(existing_ids) == set(ids):
                if show_progress:
                    print(f"Layout '{layout_key}' already exists with {len(ids)} points")
                return layout_key
            if show_progress:
                print("Layout exists but has different samples, recomputing...")

    if show_progress:
        print(f"Computing {geometry} {method} layout for {len(ids)} samples...")

    storage.ensure_layout(
        layout_key=layout_key,
        space_key=space_key,
        method=method,
        geometry=geometry,
        params=layout_params,
    )

    engine = ProjectionEngine()
    if geometry == "poincare":
        coords = engine.project_to_poincare(
            vectors,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            metric=metric,
        )
    else:
        coords = engine.project_umap(
            vectors,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            metric=metric,
        )

    storage.add_layout_coords(layout_key, ids, coords)

    return layout_key
