"""Compute orchestration pipelines for HyperView.

These functions coordinate embedding computation and layout/projection
computation, persisting results into the configured storage backend.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from hyperview.storage.backend import StorageBackend
from hyperview.storage.geometry import apply_inferred_geometry_params, resolve_geometry
from hyperview.storage.schema import make_layout_key, normalize_layout_dimension


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    total_seconds = int(round(seconds))
    minutes, secs = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m {secs:02d}s"


def compute_embeddings(
    storage: StorageBackend,
    spec: Any,
    batch_size: int = 32,
    sample_ids: list[str] | None = None,
    show_progress: bool = True,
    provider_registry: Any | None = None,
) -> tuple[str, int, int]:
    """Compute embeddings for samples that don't have them yet.

    Args:
        storage: Storage backend to read samples from and write embeddings to.
        spec: Embedding specification (provider, model_id, etc.)
        batch_size: Batch size for processing.
        sample_ids: Optional subset of sample IDs to ensure embeddings for.
            If omitted, embeddings are ensured for the full dataset.
        show_progress: Whether to show progress bar.
        provider_registry: Optional runtime provider registry to resolve
            control-plane registered providers.

    Returns:
        Tuple of (space_key, num_computed, num_skipped).

    Raises:
        ValueError: If no samples exist, requested sample IDs are missing,
            or the provider cannot be resolved.
    """
    if sample_ids is None:
        target_samples = storage.get_all_samples()
        if not target_samples:
            raise ValueError("No samples in storage")
    else:
        if not sample_ids:
            raise ValueError("sample_ids must contain at least one sample ID")

        requested_sample_ids = list(dict.fromkeys(sample_ids))
        target_samples = storage.get_samples_by_ids(requested_sample_ids)
        found_sample_ids = {sample.id for sample in target_samples}
        missing_sample_ids = [
            sample_id for sample_id in requested_sample_ids if sample_id not in found_sample_ids
        ]
        if missing_sample_ids:
            raise ValueError(
                f"Requested sample_ids were not found in storage: {missing_sample_ids[:5]}"
            )

    # Generate space key before computing (deterministic from spec)
    space_key = spec.make_space_key()
    target_sample_ids = [sample.id for sample in target_samples]

    if not storage.get_space(space_key):
        missing_ids = target_sample_ids
    elif sample_ids is None:
        missing_ids = storage.get_missing_embedding_ids(space_key)
    else:
        embedded_ids = storage.get_embedded_ids(space_key)
        missing_ids = [
            sample_id for sample_id in target_sample_ids if sample_id not in embedded_ids
        ]

    num_skipped = len(target_sample_ids) - len(missing_ids)

    if not missing_ids:
        if show_progress:
            scope = "requested" if sample_ids is not None else "all"
            print(
                f"All {len(target_sample_ids)} {scope} samples already have embeddings "
                f"in space '{space_key}'"
            )
        return space_key, 0, num_skipped

    samples_to_embed = storage.get_samples_by_ids(missing_ids)

    if show_progress and num_skipped > 0:
        print(f"Skipped {num_skipped} samples with existing embeddings")

    from hyperview.embeddings.engine import get_engine

    engine = get_engine(provider_registry=provider_registry)
    image_samples = []
    text_samples = []
    unsupported_modalities: set[str] = set()
    for sample in samples_to_embed:
        if sample.modality == "text" or (sample.filepath is None and sample.text is not None):
            text_samples.append(sample)
        elif sample.modality in {"image", "multimodal"} and sample.filepath is not None:
            image_samples.append(sample)
        else:
            unsupported_modalities.add(sample.modality)

    if unsupported_modalities:
        raise ValueError(
            "Embedding pipeline cannot route sample modalities: "
            f"{sorted(unsupported_modalities)}"
        )

    required_modalities = set()
    if image_samples:
        required_modalities.add("image")
    if text_samples:
        required_modalities.add("text")
    engine.require_modalities(spec, required_modalities)

    ids: list[str] = []
    embedding_batches: list[np.ndarray] = []
    if image_samples:
        image_embeddings = engine.embed_images(
            samples=image_samples,
            spec=spec,
            batch_size=batch_size,
            show_progress=show_progress,
        )
        ids.extend(sample.id for sample in image_samples)
        embedding_batches.append(image_embeddings)
    if text_samples:
        text_embeddings = engine.embed_texts(
            [sample.text or "" for sample in text_samples],
            spec,
            batch_size=batch_size,
            show_progress=show_progress,
        )
        ids.extend(sample.id for sample in text_samples)
        embedding_batches.append(text_embeddings)

    dimensions = {batch.shape[1] for batch in embedding_batches}
    if len(dimensions) != 1:
        raise ValueError(
            f"Provider '{spec.provider}' returned incompatible image/text embedding dimensions: "
            f"{sorted(dimensions)}"
        )
    embeddings = (
        embedding_batches[0]
        if len(embedding_batches) == 1
        else np.concatenate(embedding_batches, axis=0)
    )

    dim = embeddings.shape[1]
    config = apply_inferred_geometry_params(engine.get_space_config(spec, dim), embeddings)
    storage.ensure_space(
        model_id=spec.model_id or spec.provider,
        dim=dim,
        config=config,
        space_key=space_key,
    )

    storage.add_embeddings(space_key, ids, embeddings)

    return space_key, len(ids), num_skipped


def compute_layout(
    storage: StorageBackend,
    space_key: str | None = None,
    method: str = "umap",
    geometry: str = "euclidean",
    layout_dimension: int = 2,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    metric: str = "cosine",
    force: bool = False,
    show_progress: bool = True,
) -> str:
    """Compute layout/projection for visualization.

    Args:
        storage: Storage backend with embeddings.
        space_key: Embedding space to project. If None, uses the first available.
        method: Projection method ('umap' or 'pca').
        geometry: Output geometry type ('euclidean', 'poincare', or 'spherical').
        layout_dimension: Visualization dimension (2D or 3D).
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
    if method not in ("umap", "pca"):
        raise ValueError(f"Invalid method: {method}. Supported methods: 'umap', 'pca'.")
    layout_dimension = normalize_layout_dimension(layout_dimension)

    if geometry not in ("euclidean", "poincare", "spherical"):
        raise ValueError(
            f"Invalid geometry: {geometry}. Must be 'euclidean', 'poincare', or 'spherical'."
        )
    if geometry == "poincare" and layout_dimension != 2:
        raise ValueError("Poincare layouts currently require 2D output.")

    if space_key is None:
        spaces = storage.list_spaces()
        if not spaces:
            raise ValueError("No embedding spaces. Call compute_embeddings() first.")

        # Choose a sensible default space based on the requested output geometry.
        # - For Poincaré output, prefer a hyperbolic (hyperboloid) embedding space if present.
        # - For non-hyperbolic output, prefer a Euclidean embedding space if present.
        if geometry == "poincare":
            preferred = next((s for s in spaces if s.geometry == "hyperboloid"), None)
        else:
            preferred = next((s for s in spaces if s.geometry != "hyperboloid"), None)

        space_key = preferred.space_key if preferred is not None else spaces[0].space_key

    space = storage.get_space(space_key)
    if space is None:
        raise ValueError(f"Space not found: {space_key}")

    ids, vectors = storage.get_embeddings(space_key)
    if len(ids) == 0:
        raise ValueError(f"No embeddings in space '{space_key}'. Call compute_embeddings() first.")

    input_geometry = space.geometry
    resolved_geometry = resolve_geometry(space, vectors)
    curvature = resolved_geometry.params.get("curvature")

    min_samples = 3 if method == "umap" else 2
    if len(ids) < min_samples:
        raise ValueError(
            f"Need at least {min_samples} samples for {method} visualization, have {len(ids)}"
        )

    layout_params: dict[str, Any] | None
    if method == "umap":
        layout_params = {
            "n_neighbors": n_neighbors,
            "min_dist": min_dist,
            "metric": metric,
        }
    else:
        layout_params = None

    normalize_input = geometry == "spherical"

    layout_key = make_layout_key(
        space_key,
        method,
        geometry,
        layout_dimension=layout_dimension,
        params=layout_params,
    )

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
        print(
            f"Computing {geometry} {method} layout ({layout_dimension}D) for {len(ids)} samples..."
        )

    storage.ensure_layout(
        layout_key=layout_key,
        space_key=space_key,
        method=method,
        geometry=geometry,
        params=layout_params,
    )

    from hyperview.embeddings.projection import ProjectionEngine

    engine = ProjectionEngine()
    started_at = time.perf_counter()
    coords = engine.project(
        vectors,
        input_geometry=input_geometry,
        output_geometry=geometry,
        n_components=layout_dimension,
        normalize_input=normalize_input,
        curvature=curvature,
        method=method,
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric=metric,
        verbose=show_progress,
    )

    if show_progress:
        print(
            f"Computed {geometry} {method} layout in "
            f"{_format_elapsed(time.perf_counter() - started_at)}",
            flush=True,
        )

    storage.add_layout_coords(layout_key, ids, coords)

    return layout_key
