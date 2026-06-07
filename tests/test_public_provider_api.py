from __future__ import annotations

from pathlib import Path

import hyperview as hv


def test_public_provider_registration_api_uses_persistent_registry(
    monkeypatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "providers.json"
    monkeypatch.setattr(
        "hyperview.runtime.get_provider_registry_path",
        lambda: registry_path,
    )

    registration = hv.register_provider(
        "demo-provider",
        "demo_provider:Provider",
        description="Demo provider",
        overwrite=True,
    )

    assert registration["alias"] == "demo-provider"
    assert registry_path.exists()
    assert hv.unregister_provider("demo-provider")
