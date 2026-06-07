from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hyperview.runtime import ProviderRegistry


def test_provider_registration_does_not_import_target_module(tmp_path: Path) -> None:
    marker = tmp_path / "imported.txt"
    module_path = tmp_path / "heavy_provider.py"
    module_path.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                f"Path({str(marker)!r}).write_text('imported')",
                "class Provider:",
                "    pass",
            ]
        )
    )
    sys.path.insert(0, str(tmp_path))
    try:
        registry = ProviderRegistry(tmp_path / "providers.json")
        registration = registry.register_python("heavy", "heavy_provider:Provider")

        assert registration.alias == "heavy"
        assert not marker.exists()

        assert registry.is_available("heavy")
        assert marker.read_text() == "imported"
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("heavy_provider", None)


@pytest.mark.parametrize("import_path", ["missing_separator", ":Provider", "module:"])
def test_provider_registration_validates_import_path_shape(
    tmp_path: Path, import_path: str
) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")

    with pytest.raises(ValueError, match="import_path must use the form"):
        registry.register_python("invalid", import_path)
