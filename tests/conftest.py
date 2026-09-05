"""Keep the test suite out of the developer's real HyperView store.

`Dataset(..., persist=False)` skips writing the dataset, but workspace, provider
and job state still land in the registry directories that `StorageConfig`
resolves from the environment -- and those default to `~/.hyperview`. Without
this fixture a test run silently accumulates fixture workspaces in the same
registry the demos and Static Space exports read from, where a test's workspace
id can collide with a real one.

Redirecting `HYPERVIEW_HOME` and both storage roots at a per-session temporary
directory pins every registry path with them: `get_runtime_config_dir()` is the
home directory, so workspaces.json, providers.json and jobs.json all land there.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolate_hyperview_store(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("hyperview-store")
    datasets_dir = root / "datasets"
    media_dir = root / "media"
    datasets_dir.mkdir()
    media_dir.mkdir()

    previous = {
        "HYPERVIEW_HOME": os.environ.get("HYPERVIEW_HOME"),
        "HYPERVIEW_DATASETS_DIR": os.environ.get("HYPERVIEW_DATASETS_DIR"),
        "HYPERVIEW_MEDIA_DIR": os.environ.get("HYPERVIEW_MEDIA_DIR"),
    }
    os.environ["HYPERVIEW_HOME"] = str(root)
    os.environ["HYPERVIEW_DATASETS_DIR"] = str(datasets_dir)
    os.environ["HYPERVIEW_MEDIA_DIR"] = str(media_dir)
    try:
        yield root
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(autouse=True)
def guard_real_hyperview_store():
    """Fail loudly if a test writes into the real store despite the redirect."""

    registry = Path.home() / ".hyperview" / "workspaces.json"
    before = registry.stat().st_mtime_ns if registry.exists() else None
    yield
    after = registry.stat().st_mtime_ns if registry.exists() else None
    if before != after:
        raise AssertionError(
            f"test wrote to the real workspace registry at {registry}; "
            "it must go through the isolated store instead"
        )
