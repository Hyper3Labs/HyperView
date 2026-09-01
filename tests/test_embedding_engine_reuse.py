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


def _fake_provider_module() -> str:
    """Two interchangeable provider classes behind one import path."""

    import sys
    import types

    module = types.ModuleType("hyperview_fake_providers")

    class Alpha:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class Beta:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    module.Alpha = Alpha
    module.Beta = Beta
    sys.modules["hyperview_fake_providers"] = module
    return "hyperview_fake_providers"


def test_reregistering_an_alias_replaces_the_cached_provider(tmp_path) -> None:
    """Caching by spec alone made overwrite=True silently do nothing.

    The spec does not change when an alias is re-pointed at a different
    implementation, so the engine kept handing back the instance built from the
    previous registration. Engines used to be thrown away after every call,
    which hid this until they started being reused.
    """

    from hyperview.embeddings.engine import EmbeddingSpec

    module = _fake_provider_module()
    registry = ProviderRegistry(path=tmp_path / "providers.json")
    registry.register_python("swappable", f"{module}:Alpha")
    spec = EmbeddingSpec(provider="swappable", model_id="m1")

    assert type(get_engine(registry).get_function(spec)).__name__ == "Alpha"

    registry.register_python("swappable", f"{module}:Beta", overwrite=True)

    assert type(get_engine(registry).get_function(spec)).__name__ == "Beta"


def test_unchanged_registration_still_reuses_its_cached_provider(tmp_path) -> None:
    """The identity guard must not defeat the caching it guards."""

    from hyperview.embeddings.engine import EmbeddingSpec

    module = _fake_provider_module()
    registry = ProviderRegistry(path=tmp_path / "providers.json")
    registry.register_python("stable", f"{module}:Alpha")
    spec = EmbeddingSpec(provider="stable", model_id="m1")

    engine = get_engine(registry)

    assert engine.get_function(spec) is engine.get_function(spec)


def test_registration_identity_tracks_defaults(tmp_path) -> None:
    """Same target, different defaults, is a different provider."""

    module = _fake_provider_module()
    registry = ProviderRegistry(path=tmp_path / "providers.json")
    first = registry.register_python("cfg", f"{module}:Alpha", defaults={"dim": 128})
    second = registry.register_python(
        "cfg", f"{module}:Alpha", defaults={"dim": 256}, overwrite=True
    )

    assert first.identity() != second.identity()
