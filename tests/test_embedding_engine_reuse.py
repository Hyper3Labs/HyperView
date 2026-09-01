"""An engine must outlive the call that asked for it.

`EmbeddingEngine` caches the embedding functions it loads, so the cache is only
worth anything if repeated calls get the same engine. `get_engine` used to
return a fresh one whenever a provider registry was passed -- which the runtime
does on every request -- so each text query re-resolved and re-loaded a full
image+text model. Queries took tens of seconds and pinned a core.
"""

from __future__ import annotations

import gc
import weakref

from hyperview.embeddings.engine import EmbeddingEngine, get_engine
from hyperview.runtime import ProviderRegistry


def test_same_registry_reuses_one_engine(tmp_path) -> None:
    registry = ProviderRegistry(path=tmp_path / "providers.json")

    assert get_engine(registry) is get_engine(registry)


def test_distinct_registries_get_distinct_engines(tmp_path) -> None:
    first = ProviderRegistry(path=tmp_path / "first.json")
    second = ProviderRegistry(path=tmp_path / "second.json")

    assert get_engine(first) is not get_engine(second)


def test_engine_bound_to_the_registry_it_was_asked_for(tmp_path) -> None:
    registry = ProviderRegistry(path=tmp_path / "providers.json")

    assert get_engine(registry).provider_registry is registry


def test_calls_without_a_registry_share_the_process_singleton() -> None:
    assert get_engine() is get_engine()
    assert isinstance(get_engine(), EmbeddingEngine)


def test_engine_does_not_outlive_its_registry(tmp_path) -> None:
    """The engine holds loaded models; pinning dead registries would leak them."""

    registry = ProviderRegistry(path=tmp_path / "providers.json")
    get_engine(registry)
    observed = weakref.ref(registry)

    del registry
    gc.collect()

    assert observed() is None


def test_cached_embedding_functions_survive_across_calls(tmp_path) -> None:
    """The point of reuse: a loaded function is still cached on the next call."""

    registry = ProviderRegistry(path=tmp_path / "providers.json")
    get_engine(registry)._cache["sentinel"] = object()

    assert "sentinel" in get_engine(registry)._cache
