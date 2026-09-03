"""`hyperview publish` takes an exported bundle to a host.

Every test here is offline: the Hugging Face client and the Wrangler subprocess
are the only two ways this module reaches the network, and both are replaced.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from hyperview import Dataset
from hyperview.cli import main
from hyperview.core.sample import Sample
from hyperview.publish import (
    parse_target,
    publish,
    render_dockerfile,
    render_readme,
)
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry
from hyperview.static_export import export_runtime_workspace


def _export_bundle(root: Path) -> Path:
    """Export a small synthetic workspace and return its bundle directory."""

    media_dir = root / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    dataset = Dataset("publish_demo_dataset", persist=False)
    sample_ids: list[str] = []
    for index, label in enumerate(["cat", "dog", "cat"]):
        image_path = media_dir / f"sample-{index}.png"
        Image.new("RGB", (12 + index, 10 + index), (index * 40, 40, 180)).save(image_path)
        sample_id = f"sample-{index}"
        sample_ids.append(sample_id)
        dataset.add_sample(
            Sample(
                id=sample_id,
                filepath=str(image_path),
                label=label,
                metadata={"index": index},
            )
        )
    layout_key = dataset.set_coords(
        "euclidean",
        sample_ids,
        np.asarray([[0.0, 0.0], [1.0, 0.5], [2.0, 0.25]], dtype=np.float32),
    )
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(root / "providers.json"),
        workspace_registry=WorkspaceRegistry(root / "workspaces.json"),
    )
    runtime.attach_dataset_instance("research", dataset, activate_workspace=True)
    runtime.set_active_layout("research", layout_key)

    bundle_dir = root / "bundle"
    export_runtime_workspace(runtime, "research", bundle_dir)
    return bundle_dir


@pytest.fixture(scope="module")
def bundle_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _export_bundle(tmp_path_factory.mktemp("publish-bundle"))


@pytest.fixture
def manifest(bundle_dir: Path) -> dict:
    return json.loads((bundle_dir / "hyperview-static.json").read_text(encoding="utf-8"))


def _staged_api(recorder: dict) -> MagicMock:
    """An HfApi double that records the staged folder before it is torn down."""

    api = MagicMock()

    def _capture(**kwargs):
        folder = Path(kwargs["folder_path"])
        recorder["folder_path"] = folder
        recorder["files"] = sorted(
            str(path.relative_to(folder)) for path in folder.rglob("*") if path.is_file()
        )
        dockerfile = folder / "Dockerfile"
        if dockerfile.is_file():
            recorder["dockerfile"] = dockerfile.read_text(encoding="utf-8")
        return MagicMock(oid="deadbeef")

    api.upload_folder.side_effect = _capture
    return api


# --- target parsing -------------------------------------------------------


def test_parse_target_reads_each_supported_form() -> None:
    assert parse_target("hf:hyper3labs/demo") == ("hf", "hyper3labs/demo")
    assert parse_target("cloudflare") == ("cloudflare", "")
    assert parse_target("dir:/srv/site/spaces/demo") == ("dir", "/srv/site/spaces/demo")


@pytest.mark.parametrize(
    "value",
    ["", "hf:", "hf:demo", "hf:owner/name/extra", "s3:bucket", "dir:"],
)
def test_parse_target_rejects_malformed_targets(value: str) -> None:
    with pytest.raises(ValueError):
        parse_target(value)


# --- Hugging Face Static Space -------------------------------------------


def test_hf_static_publish_creates_a_static_space_and_replaces_its_files(
    bundle_dir: Path,
) -> None:
    recorder: dict = {}
    api = _staged_api(recorder)

    with patch("hyperview.publish._hf_api", return_value=api) as factory:
        result = publish(bundle_dir, to="hf:hyper3labs/research-demo", mode="static")

    factory.assert_called_once_with(None)
    api.create_repo.assert_called_once_with(
        repo_id="hyper3labs/research-demo",
        repo_type="space",
        space_sdk="static",
        private=False,
        exist_ok=True,
    )
    api.request_space_hardware.assert_not_called()
    upload = api.upload_folder.call_args.kwargs
    assert upload["repo_id"] == "hyper3labs/research-demo"
    assert upload["repo_type"] == "space"
    # Stale files from a previous publish must not survive the new one.
    assert upload["delete_patterns"] == ["*"]
    assert upload["commit_message"] == "Publish HyperView static Space"

    # The bundle is uploaded from a staging copy, so index.html is at the root
    # and the user's bundle directory is never written to.
    assert "index.html" in recorder["files"]
    assert "README.md" in recorder["files"]
    assert "hyperview-static.json" in recorder["files"]
    assert "Dockerfile" not in recorder["files"]
    assert not (bundle_dir / "README.md").exists()
    assert result.url == "https://huggingface.co/spaces/hyper3labs/research-demo"
    assert result.dry_run is False


def test_hf_static_publish_honors_private_and_commit_message(bundle_dir: Path) -> None:
    api = _staged_api({})

    with patch("hyperview.publish._hf_api", return_value=api):
        publish(
            bundle_dir,
            to="hf:hyper3labs/research-demo",
            private=True,
            commit_message="Refresh the gallery demo",
        )

    assert api.create_repo.call_args.kwargs["private"] is True
    assert api.upload_folder.call_args.kwargs["commit_message"] == "Refresh the gallery demo"


def test_hf_static_publish_requires_an_index_at_the_bundle_root(
    bundle_dir: Path, tmp_path: Path
) -> None:
    broken = tmp_path / "no-index"
    shutil.copytree(bundle_dir, broken)
    (broken / "index.html").unlink()

    with pytest.raises(RuntimeError, match="index.html"):
        publish(broken, to="hf:hyper3labs/research-demo")


# --- Hugging Face Live Space ---------------------------------------------


def test_hf_live_publish_creates_a_docker_space_with_a_generated_image(
    bundle_dir: Path,
) -> None:
    recorder: dict = {}
    api = _staged_api(recorder)

    with patch("hyperview.publish._hf_api", return_value=api):
        result = publish(
            bundle_dir,
            to="hf:hyper3labs/research-live",
            mode="live",
            hardware="cpu-upgrade",
            extra_pip=["torch==2.9.1"],
        )

    api.create_repo.assert_called_once_with(
        repo_id="hyper3labs/research-live",
        repo_type="space",
        space_sdk="docker",
        private=False,
        exist_ok=True,
    )
    api.request_space_hardware.assert_called_once_with(
        repo_id="hyper3labs/research-live", hardware="cpu-upgrade"
    )
    assert api.upload_folder.call_args.kwargs["delete_patterns"] == ["*"]

    files = recorder["files"]
    assert "Dockerfile" in files
    assert "README.md" in files
    # The bundle sits in its own subdirectory so the image can COPY it whole.
    assert "bundle/index.html" in files
    assert "bundle/hyperview-static.json" in files
    assert "index.html" not in files

    assert "torch==2.9.1" in result.plan.generated_files["Dockerfile"]
    assert recorder["dockerfile"] == result.plan.generated_files["Dockerfile"]


# --- generated files ------------------------------------------------------


def test_dockerfile_pins_the_manifest_versions_and_serves_the_bundle(manifest: dict) -> None:
    manifest = dict(manifest)
    manifest["hyperview_version"] = "1.2.3"
    manifest["pins"] = {"hyper_models": "0.3.1"}

    dockerfile = render_dockerfile(manifest)

    assert dockerfile.startswith("FROM python:3.11-slim")
    assert '"hyperview==1.2.3"' in dockerfile
    assert '"hyper-models==0.3.1"' in dockerfile
    assert "RUN useradd -m -u 1000 user" in dockerfile
    assert "USER user" in dockerfile
    assert "COPY --chown=user bundle /home/user/app/bundle" in dockerfile
    assert "ENV HYPERVIEW_NO_AUTH=1" in dockerfile
    assert "ENV HYPERVIEW_DATASETS_DIR=/home/user/app/data/datasets" in dockerfile
    assert "HYPERVIEW_MEDIA_DIR=/home/user/app/data/media" in dockerfile
    assert "EXPOSE 7860" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "http://localhost:7860/api/runtime" in dockerfile
    assert '"hyperview", "serve"' in dockerfile
    assert '"--from", "/home/user/app/bundle"' in dockerfile
    # The image owns the bundle for the life of the container, so restore points
    # at its media instead of copying it into the datasets dir a second time.
    assert '"--link-media"' in dockerfile
    assert "points at the bundle's own media instead of copying it" in dockerfile
    assert '"--host", "0.0.0.0"' in dockerfile
    assert '"--port", "7860"' in dockerfile
    assert '"--public"' in dockerfile
    # The comment has to say what NO_AUTH actually does, or the next reader
    # assumes the Space is unprotected.
    assert "It marks the server public" in dockerfile
    assert "provider registration" in dockerfile


def test_live_plan_flags_a_pin_pip_will_not_find(bundle_dir: Path, manifest: dict) -> None:
    result = publish(bundle_dir, to="hf:hyper3labs/research-live", mode="live", dry_run=True)

    is_dev_build = ".dev" in str(manifest["hyperview_version"])
    flagged = any("unlikely to be on PyPI" in note for note in result.plan.notes)
    assert flagged is is_dev_build


def test_dockerfile_follows_the_python_version_the_manifest_records(manifest: dict) -> None:
    manifest = dict(manifest)
    manifest["runtime"] = {"python_version": "3.12.4"}

    assert render_dockerfile(manifest).startswith("FROM python:3.12-slim")


def test_dockerfile_accepts_pins_written_as_requirement_strings(manifest: dict) -> None:
    manifest = dict(manifest)
    manifest["environment"] = {"packages": ["hyper-models==0.4.0", "datasets==4.5.0"]}

    dockerfile = render_dockerfile(manifest)

    assert '"hyper-models==0.4.0"' in dockerfile
    assert '"datasets==4.5.0"' in dockerfile


def test_static_readme_carries_static_frontmatter(manifest: dict) -> None:
    readme = render_readme(manifest, mode="static")
    head, _, body = readme.partition("---\n\n")

    assert head.startswith("---\n")
    assert "sdk: static" in head
    assert "app_port" not in head
    assert "pinned: false" in head
    assert "title: HyperView Research" in head
    assert "emoji: " in head
    assert "short_description: " in head
    assert "publish_demo_dataset" in body


def test_live_readme_declares_the_docker_sdk_and_port(manifest: dict) -> None:
    readme = render_readme(manifest, mode="live")

    assert "sdk: docker" in readme
    assert "app_port: 7860" in readme


def test_readme_title_and_emoji_can_be_overridden(manifest: dict) -> None:
    readme = render_readme(manifest, mode="static", title="Jaguar Re-ID", emoji="🐆")

    assert "title: Jaguar Re-ID" in readme
    assert "emoji: 🐆" in readme
    assert "# Jaguar Re-ID" in readme


# --- dir: target ----------------------------------------------------------


def test_dir_target_copies_the_bundle_onto_the_packaged_frontend(
    bundle_dir: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "site" / "spaces" / "research"

    result = publish(bundle_dir, to=f"dir:{destination}")

    assert result.output_dir == destination.resolve()
    assert (destination / "index.html").is_file()
    assert (destination / "hyperview-static.json").is_file()
    assert (destination / "api" / "runtime.json").is_file()
    assert result.plan.num_files > 0


def test_dir_target_rejects_a_live_mode(bundle_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Hugging Face targets only"):
        publish(bundle_dir, to=f"dir:{tmp_path / 'site'}", mode="live")


# --- Cloudflare -----------------------------------------------------------


def test_cloudflare_runs_the_command_the_manifest_records_from_the_bundle(
    bundle_dir: Path,
) -> None:
    with (
        patch("hyperview.publish.shutil.which", return_value="/usr/bin/npx"),
        patch("hyperview.publish.subprocess.run") as run,
    ):
        result = publish(bundle_dir, to="cloudflare")

    run.assert_called_once_with(
        ["npx", "wrangler", "deploy", "--config", "wrangler.jsonc"],
        cwd=str(bundle_dir),
        check=True,
    )
    assert result.plan.command == ["npx", "wrangler", "deploy", "--config", "wrangler.jsonc"]


def test_cloudflare_project_flag_rewrites_the_worker_name(
    bundle_dir: Path, tmp_path: Path
) -> None:
    copy = tmp_path / "cf-bundle"
    shutil.copytree(bundle_dir, copy)

    with (
        patch("hyperview.publish.shutil.which", return_value="/usr/bin/npx"),
        patch("hyperview.publish.subprocess.run"),
    ):
        result = publish(copy, to="cloudflare", project="gallery-research")

    config = json.loads((copy / "wrangler.jsonc").read_text(encoding="utf-8"))
    assert config["name"] == "gallery-research"
    # The rest of the generated configuration survives the rename.
    assert config["assets"]["directory"] == "."
    assert result.plan.destination == "gallery-research"


def test_cloudflare_explains_a_missing_wrangler_instead_of_failing_obscurely(
    bundle_dir: Path,
) -> None:
    with (
        patch("hyperview.publish.shutil.which", return_value=None),
        patch("hyperview.publish.subprocess.run") as run,
        pytest.raises(RuntimeError, match="npx is not on PATH"),
    ):
        publish(bundle_dir, to="cloudflare")

    run.assert_not_called()


def test_cloudflare_reports_a_failed_deploy(bundle_dir: Path) -> None:
    failure = subprocess.CalledProcessError(1, ["npx", "wrangler", "deploy"])

    with (
        patch("hyperview.publish.shutil.which", return_value="/usr/bin/npx"),
        patch("hyperview.publish.subprocess.run", side_effect=failure),
        pytest.raises(RuntimeError, match="exit code 1"),
    ):
        publish(bundle_dir, to="cloudflare")


# --- dry runs -------------------------------------------------------------


def test_dry_run_never_reaches_hugging_face(bundle_dir: Path) -> None:
    with patch("hyperview.publish._hf_api", side_effect=AssertionError("network")) as factory:
        static = publish(bundle_dir, to="hf:hyper3labs/research-demo", dry_run=True)
        live = publish(bundle_dir, to="hf:hyper3labs/research-live", mode="live", dry_run=True)

    factory.assert_not_called()
    assert static.dry_run is True
    assert "README.md" in static.plan.generated_files
    assert "Dockerfile" not in static.plan.generated_files
    assert "Dockerfile" in live.plan.generated_files
    assert live.plan.packages["hyperview"]
    assert not (bundle_dir / "README.md").exists()
    assert not (bundle_dir / "Dockerfile").exists()


def test_dry_run_writes_nothing_to_a_dir_target(bundle_dir: Path, tmp_path: Path) -> None:
    destination = tmp_path / "site" / "spaces" / "research"

    result = publish(bundle_dir, to=f"dir:{destination}", dry_run=True)

    assert result.dry_run is True
    assert not destination.exists()


def test_dry_run_does_not_deploy_or_rewrite_cloudflare_config(
    bundle_dir: Path, tmp_path: Path
) -> None:
    copy = tmp_path / "cf-dry"
    shutil.copytree(bundle_dir, copy)
    before = (copy / "wrangler.jsonc").read_text(encoding="utf-8")

    with patch("hyperview.publish.subprocess.run") as run:
        result = publish(copy, to="cloudflare", project="renamed", dry_run=True)

    run.assert_not_called()
    assert (copy / "wrangler.jsonc").read_text(encoding="utf-8") == before
    assert result.plan.command == ["npx", "wrangler", "deploy", "--config", "wrangler.jsonc"]


# --- manifest and CLI -----------------------------------------------------


def test_manifest_describes_where_the_bundle_can_be_published(manifest: dict) -> None:
    targets = manifest["deployment"]["targets"]

    assert targets["static"]["space"] == "Static Space"
    assert targets["live"]["space"] == "Live Space"
    assert any("--to cloudflare" in command for command in targets["static"]["commands"])
    assert any("dir:" in command for command in targets["static"]["commands"])
    assert any("--mode live" in command for command in targets["live"]["commands"])
    # The pre-existing deployment description is preserved.
    assert manifest["deployment"]["cloudflare"]["command"]
    assert manifest["deployment"]["hosting"] == {"mode": "static-assets"}


def test_cli_dry_run_prints_the_static_plan(bundle_dir: Path, capsys) -> None:
    main(["publish", str(bundle_dir), "--to", "hf:test/x", "--mode", "static", "--dry-run"])

    out = capsys.readouterr().out
    assert "Dry run" in out
    assert "test/x" in out
    assert "sdk: static" in out
    assert "Dockerfile" not in out


def test_cli_dry_run_prints_the_live_plan_with_the_dockerfile(bundle_dir: Path, capsys) -> None:
    main(["publish", str(bundle_dir), "--to", "hf:test/x", "--mode", "live", "--dry-run"])

    out = capsys.readouterr().out
    assert "Live Space" in out
    assert "----- Dockerfile -----" in out
    assert "hyperview serve" in out or '"--from"' in out
    assert "sdk: docker" in out


def test_cli_json_dry_run_is_machine_readable(bundle_dir: Path, capsys) -> None:
    main(["publish", str(bundle_dir), "--to", "dir:/tmp/nowhere", "--dry-run", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["publish"]["dry_run"] is True
    assert payload["publish"]["plan"]["target"] == "dir"
    assert not Path("/tmp/nowhere").exists()


def test_extra_pip_overrides_a_manifest_pin_by_name() -> None:
    from hyperview.publish import _requirements

    packages = {"hyperview": "1.0.1.dev1+gabc", "hyper-models": "0.3.1"}
    assert _requirements(packages, ("hyperview==1.1.0", "torch==2.4.0")) == [
        "hyperview==1.1.0",
        "hyper-models==0.3.1",
        "torch==2.4.0",
    ]
    assert _requirements(packages, ("Hyper_Models==0.4.0",)) == [
        "hyperview==1.0.1.dev1+gabc",
        "Hyper_Models==0.4.0",
    ]


def test_plan_reports_the_overridden_pin_not_the_manifest_one(tmp_path, monkeypatch) -> None:
    from hyperview.publish import _effective_packages

    assert _effective_packages({"hyperview": "1.0.1.dev1+gabc"}, ("hyperview==1.1.0",)) == {
        "hyperview": "1.1.0"
    }
    assert _effective_packages({"hyperview": "1.1.0"}, ("torch==2.4.0",)) == {"hyperview": "1.1.0"}


def test_dockerfile_reads_producer_pins_and_runs_pre_install_first() -> None:
    from hyperview.publish import render_dockerfile

    manifest = {
        "hyperview_version": "1.1.0",
        "producer": {"hyperview": "1.1.0", "hyper_models": "0.3.1", "python": "3.11.11"},
    }
    dockerfile = render_dockerfile(
        manifest,
        extra_pip=("hyper-models[ml]==0.3.1",),
        pre_install=("torch torchvision --index-url https://download.pytorch.org/whl/cpu",),
    )
    pre = dockerfile.index("RUN pip install torch torchvision --index-url")
    pinned = dockerfile.index('"hyperview==1.1.0"')
    assert pre < pinned
    assert '"hyper-models[ml]==0.3.1"' in dockerfile
    assert '"hyper-models==0.3.1"' not in dockerfile
