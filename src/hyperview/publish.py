"""Publish an exported HyperView bundle to a hosting target.

`hyperview export` writes a bundle directory; that directory is the unit of
delivery. This module takes such a bundle and puts it somewhere people can open:

* **Static Space** -- the bundle's files on a static host. Hugging Face with
  ``space_sdk="static"``, Cloudflare Workers static assets, or a plain directory
  inside a containing site.
* **Live Space** -- a container that runs ``hyperview serve --from <bundle>
  --public``, so visitors also get text queries, model jobs, and computed
  layouts. Hugging Face with ``space_sdk="docker"``.

Nothing here reaches the network while ``dry_run`` is set: a dry run renders the
plan (including the generated Dockerfile and README) into a temporary directory
and prints it.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hyperview._version import __version__
from hyperview.static_export import (
    _bundle_stats,
    _read_static_bundle_manifest,
    copy_static_bundle,
)

DEFAULT_PYTHON_VERSION = "3.11"
DEFAULT_EMOJI = "🔭"
LIVE_SPACE_PORT = 7860
LIVE_APP_DIR = "/home/user/app"
LIVE_BUNDLE_DIR = f"{LIVE_APP_DIR}/bundle"
LIVE_DATA_DIR = f"{LIVE_APP_DIR}/data"
HF_MISSING_MESSAGE = (
    "Publishing to Hugging Face needs the huggingface_hub client, which is not "
    "installed. Install it with: pip install 'hyperview[publish]' "
    "(or: pip install 'huggingface-hub>=1.11,<2')."
)
# Copied verbatim from the demo Spaces because the nuance matters: the flag does
# not disable the permission model, it publishes the viewer half of it.
NO_AUTH_COMMENT = (
    "# HyperView mints a session token and rejects unauthenticated runtime\n"
    "# commands. A public Space has no way to hand visitors that token, so panel\n"
    "# creation and case switching 401 without this. It marks the server public:\n"
    "# visitors get the viewer commands and nothing else, so provider registration,\n"
    "# extension install, tool execution and compute stay closed."
)


@dataclass(frozen=True)
class PublishPlan:
    """What a publish would do, before it does it."""

    target: str
    mode: str
    bundle_dir: Path
    destination: str
    num_files: int
    bundle_bytes: int
    private: bool = False
    hardware: str | None = None
    packages: dict[str, str] = field(default_factory=dict)
    generated_files: dict[str, str] = field(default_factory=dict)
    command: list[str] | None = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "mode": self.mode,
            "bundle_dir": str(self.bundle_dir),
            "destination": self.destination,
            "num_files": self.num_files,
            "bundle_bytes": self.bundle_bytes,
            "private": self.private,
            "hardware": self.hardware,
            "packages": dict(self.packages),
            "generated_files": dict(self.generated_files),
            "command": list(self.command) if self.command is not None else None,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class PublishResult:
    plan: PublishPlan
    dry_run: bool
    url: str | None = None
    output_dir: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "dry_run": self.dry_run,
            "url": self.url,
            "output_dir": str(self.output_dir) if self.output_dir is not None else None,
        }


def parse_target(to: str) -> tuple[str, str]:
    """Split ``--to`` into a target kind and its destination.

    ``hf:owner/name`` -> ``("hf", "owner/name")``; ``cloudflare`` ->
    ``("cloudflare", "")``; ``dir:/path/to/site`` -> ``("dir", "/path/to/site")``.
    """

    value = (to or "").strip()
    if not value:
        raise ValueError("--to is required, for example --to hf:owner/name")
    if value == "cloudflare":
        return "cloudflare", ""
    kind, separator, rest = value.partition(":")
    kind = kind.strip().lower()
    rest = rest.strip()
    if not separator or not rest:
        raise ValueError(
            f"Unsupported publish target: {to!r}. Use hf:<owner>/<name>, cloudflare, or dir:<path>."
        )
    if kind == "hf":
        owner, slash, name = rest.partition("/")
        if not slash or not owner.strip() or not name.strip() or "/" in name:
            raise ValueError(f"A Hugging Face target must be hf:<owner>/<name>, got {to!r}")
        return "hf", rest
    if kind == "dir":
        return "dir", rest
    if kind == "cloudflare":
        return "cloudflare", rest
    raise ValueError(
        f"Unsupported publish target: {to!r}. Use hf:<owner>/<name>, cloudflare, or dir:<path>."
    )


def _hf_api(token: str | None = None):
    """Build an authenticated ``HfApi``.

    Kept as a module-level factory so the network client has exactly one seam,
    which the tests replace.
    """

    try:
        from huggingface_hub import HfApi
    except ImportError as exc:  # pragma: no cover - exercised through a patched import
        raise ImportError(HF_MISSING_MESSAGE) from exc
    resolved = token or os.environ.get("HF_TOKEN")
    return HfApi(token=resolved) if resolved else HfApi()


def _humanize(workspace_id: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", workspace_id) if word]
    if not words:
        return "Workspace"
    return " ".join(word if word.isupper() else word.capitalize() for word in words)


def _manifest_section(manifest: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = manifest.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _workspace_id(manifest: dict[str, Any]) -> str:
    workspace = _manifest_section(manifest, "workspace")
    return str(workspace.get("id") or "workspace")


def _dataset_name(manifest: dict[str, Any]) -> str | None:
    workspace = _manifest_section(manifest, "workspace")
    name = workspace.get("dataset_name") or manifest.get("dataset_name")
    return str(name) if name else None


def _python_version(manifest: dict[str, Any]) -> str:
    """Read the Python version the bundle was exported under, if it records one."""

    candidates = [
        manifest.get("python_version"),
        _manifest_section(manifest, "runtime", "environment").get("python_version"),
        _manifest_section(manifest, "runtime", "environment").get("python"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        match = re.match(r"^(\d+\.\d+)", str(candidate))
        if match:
            return match.group(1)
    return DEFAULT_PYTHON_VERSION


def _normalize_pins(value: Any) -> dict[str, str]:
    """Accept either ``{"hyper-models": "0.3.1"}`` or ``["hyper-models==0.3.1"]``."""

    pins: dict[str, str] = {}
    if isinstance(value, dict):
        for name, version in value.items():
            if isinstance(version, str) and version:
                pins[str(name).replace("_", "-")] = version
            elif isinstance(version, dict) and isinstance(version.get("version"), str):
                pins[str(name).replace("_", "-")] = version["version"]
    elif isinstance(value, list):
        for entry in value:
            if not isinstance(entry, str) or "==" not in entry:
                continue
            name, _, version = entry.partition("==")
            if name.strip() and version.strip():
                pins[name.strip().replace("_", "-")] = version.strip()
    return pins


def _manifest_packages(manifest: dict[str, Any]) -> dict[str, str]:
    """Collect package pins from wherever the exporter recorded them.

    The manifest is written by an exporter that evolves independently of this
    module, so every lookup here is optional and the shapes are read leniently.
    """

    packages: dict[str, str] = {}
    hyperview_version = manifest.get("hyperview_version")
    packages["hyperview"] = str(hyperview_version) if hyperview_version else __version__

    sources: list[Any] = [
        manifest.get("pins"),
        manifest.get("packages"),
        manifest.get("dependencies"),
    ]
    for section in ("runtime", "environment", "models", "providers"):
        block = _manifest_section(manifest, section)
        sources.extend([block.get("pins"), block.get("packages"), block.get("dependencies")])
    for source in sources:
        for name, version in _normalize_pins(source).items():
            packages.setdefault(name, version)
    # An older manifest may name the model package directly.
    for key in ("hyper_models_version", "hyper-models-version"):
        version = manifest.get(key)
        if version:
            packages.setdefault("hyper-models", str(version))
    return packages


def _requirements(packages: dict[str, str], extra_pip: tuple[str, ...]) -> list[str]:
    """Pin what the manifest records, letting ``extra_pip`` override by name.

    A bundle exported from a working tree records a development version; passing
    ``--extra-pip hyperview==1.1.0`` must replace that pin, not sit next to it,
    or pip refuses the two conflicting specifiers.
    """

    overrides = {_requirement_name(spec): spec for spec in extra_pip}
    requirements = [
        overrides.pop(name, f"{name}=={version}") for name, version in packages.items()
    ]
    requirements.extend(overrides.values())
    return requirements


def _requirement_name(spec: str) -> str:
    """The distribution name of a pip requirement, normalised like ``packages``."""

    name = re.split(r"[=<>!~\[; ]", spec.strip(), maxsplit=1)[0]
    return name.lower().replace("_", "-")


def _unpublishable_pin_notes(packages: dict[str, str]) -> list[str]:
    """Warn about pins pip will not find, before the image build discovers it.

    A bundle exported from a working tree records a development version such as
    ``1.0.1.dev1+g5396720``, which is not on PyPI. The Space would build for
    several minutes and then fail on the install step.
    """

    notes = []
    for name, version in packages.items():
        if ".dev" in version or "+" in version:
            notes.append(
                f"{name}=={version} is a development version and is unlikely to be on PyPI. "
                f"Publish from a released HyperView, or pass --extra-pip '{name}==<released>' to override the pin."
            )
    return notes


def _short_description(manifest: dict[str, Any], mode: str) -> str:
    dataset_name = _dataset_name(manifest)
    kind = "Live Space" if mode == "live" else "Static Space"
    text = f"HyperView {kind}"
    if dataset_name:
        text = f"{text} for {dataset_name}"
    # Hugging Face truncates short_description in the card UI; keep it in range.
    return text[:60]


def _frontmatter(fields: list[tuple[str, Any]]) -> str:
    lines = ["---"]
    for key, value in fields:
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def render_readme(
    manifest: dict[str, Any],
    *,
    mode: str,
    title: str | None = None,
    emoji: str | None = None,
) -> str:
    """Render the Space README, whose YAML frontmatter configures the Space."""

    workspace_id = _workspace_id(manifest)
    dataset_name = _dataset_name(manifest)
    resolved_title = title or f"HyperView {_humanize(workspace_id)}"
    resolved_emoji = emoji or DEFAULT_EMOJI
    fields: list[tuple[str, Any]] = [
        ("title", resolved_title),
        ("emoji", resolved_emoji),
        ("colorFrom", "blue"),
        ("colorTo", "green"),
    ]
    if mode == "live":
        fields += [("sdk", "docker"), ("app_port", LIVE_SPACE_PORT)]
    else:
        fields += [("sdk", "static")]
    fields += [
        ("pinned", False),
        ("short_description", _short_description(manifest, mode)),
    ]

    capabilities = _manifest_section(manifest, "capabilities")
    body = [
        f"# {resolved_title}",
        "",
    ]
    if mode == "live":
        body += [
            "A HyperView **Live Space**: the container runs the HyperView server over an",
            "exported workspace bundle, so visitors can browse the prepared view and also",
            "run new text queries, layouts, and model jobs.",
        ]
    else:
        body += [
            "A HyperView **Static Space**: a read-only export of a prepared workspace.",
            "Visitors browse samples and media, switch prepared cases, pan and zoom the",
            "embedding layouts, select points, and read the panels. Nothing runs a model,",
            "a database, or a Python process for a visitor.",
        ]
    body += [
        "",
        "## Contents",
        "",
        f"- Workspace: `{workspace_id}`",
    ]
    if dataset_name:
        body.append(f"- Dataset: `{dataset_name}`")
    hyperview_version = manifest.get("hyperview_version")
    if hyperview_version:
        body.append(f"- Exported with HyperView `{hyperview_version}`")
    if capabilities:
        enabled = sorted(
            key for key, value in capabilities.items() if isinstance(value, bool) and value
        )
        if enabled:
            body.append(f"- Capabilities: {', '.join(enabled)}")
    body += [
        "",
        "Built with [HyperView](https://github.com/Hyper3Labs/HyperView).",
        "",
    ]
    return f"{_frontmatter(fields)}\n\n" + "\n".join(body)


def render_dockerfile(
    manifest: dict[str, Any],
    *,
    extra_pip: tuple[str, ...] = (),
) -> str:
    """Render the Live Space Dockerfile that serves the bundle."""

    python_version = _python_version(manifest)
    packages = _manifest_packages(manifest)
    requirements = _requirements(packages, extra_pip)
    install = " \\\n    ".join(f'"{requirement}"' for requirement in requirements)
    return "\n".join(
        [
            f"FROM python:{python_version}-slim",
            "",
            "RUN apt-get update && apt-get install -y --no-install-recommends \\",
            "    curl \\",
            "    && rm -rf /var/lib/apt/lists/*",
            "",
            "RUN useradd -m -u 1000 user",
            "USER user",
            "",
            "ENV HOME=/home/user \\",
            "    PATH=/home/user/.local/bin:$PATH \\",
            "    HF_HOME=/home/user/.cache/huggingface \\",
            "    PYTHONUNBUFFERED=1 \\",
            "    PIP_NO_CACHE_DIR=1",
            "",
            f"WORKDIR {LIVE_APP_DIR}",
            "",
            "RUN pip install --upgrade pip",
            f"RUN pip install \\\n    {install}",
            "",
            "# The bundle is the unit of delivery: `hyperview serve --from` restores the",
            "# exported workspace, dataset, and layouts from it at startup.",
            f"COPY --chown=user bundle {LIVE_BUNDLE_DIR}",
            f"RUN mkdir -p {LIVE_DATA_DIR}/datasets {LIVE_DATA_DIR}/media",
            "",
            NO_AUTH_COMMENT,
            "ENV HYPERVIEW_NO_AUTH=1",
            f"ENV HYPERVIEW_DATASETS_DIR={LIVE_DATA_DIR}/datasets \\",
            f"    HYPERVIEW_MEDIA_DIR={LIVE_DATA_DIR}/media",
            "",
            f"EXPOSE {LIVE_SPACE_PORT}",
            "",
            "HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \\",
            f"    CMD curl -f http://localhost:{LIVE_SPACE_PORT}/api/runtime || exit 1",
            "",
            'CMD ["hyperview", "serve", \\',
            f'     "--from", "{LIVE_BUNDLE_DIR}", \\',
            '     "--host", "0.0.0.0", \\',
            f'     "--port", "{LIVE_SPACE_PORT}", \\',
            '     "--public"]',
            "",
        ]
    )


def _load_bundle(bundle_dir: str | Path) -> tuple[Path, dict[str, Any]]:
    resolved = Path(bundle_dir).expanduser().resolve()
    manifest = _read_static_bundle_manifest(resolved)
    return resolved, manifest


def _stage_hf(
    staging_dir: Path,
    bundle_dir: Path,
    generated: dict[str, str],
    *,
    mode: str,
    copy_bundle: bool,
) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    if copy_bundle:
        destination = staging_dir / "bundle" if mode == "live" else staging_dir
        shutil.copytree(bundle_dir, destination, dirs_exist_ok=True)
    for name, content in generated.items():
        (staging_dir / name).write_text(content, encoding="utf-8")


def _publish_to_hf(
    bundle_dir: Path,
    manifest: dict[str, Any],
    repo_id: str,
    *,
    mode: str,
    private: bool,
    dry_run: bool,
    title: str | None,
    emoji: str | None,
    extra_pip: tuple[str, ...],
    hardware: str | None,
    commit_message: str | None,
    token: str | None,
) -> PublishResult:
    if mode not in {"static", "live"}:
        raise ValueError(f"Unsupported publish mode: {mode!r}. Use static or live.")
    if mode == "static" and not (bundle_dir / "index.html").is_file():
        raise RuntimeError(
            f"A Static Space needs index.html at the bundle root, which {bundle_dir} does not "
            "have. Re-export the workspace with `hyperview export`."
        )

    generated = {"README.md": render_readme(manifest, mode=mode, title=title, emoji=emoji)}
    packages: dict[str, str] = {}
    if mode == "live":
        packages = _manifest_packages(manifest)
        generated["Dockerfile"] = render_dockerfile(manifest, extra_pip=extra_pip)

    num_files, bundle_bytes = _bundle_stats(bundle_dir)
    space_sdk = "docker" if mode == "live" else "static"
    notes: list[str] = []
    if mode == "live":
        if not manifest.get("hyperview_version"):
            notes.append(
                f"The manifest records no hyperview_version; pinned the running {__version__}."
            )
        notes.extend(_unpublishable_pin_notes(packages))
    plan = PublishPlan(
        target="hf",
        mode=mode,
        bundle_dir=bundle_dir,
        destination=repo_id,
        num_files=num_files,
        bundle_bytes=bundle_bytes,
        private=private,
        hardware=hardware,
        packages=packages,
        generated_files=generated,
        notes=tuple(notes),
    )
    url = f"https://huggingface.co/spaces/{repo_id}"

    with tempfile.TemporaryDirectory(prefix="hyperview-publish-") as temp_dir:
        staging_dir = Path(temp_dir) / "space"
        _stage_hf(
            staging_dir,
            bundle_dir,
            generated,
            mode=mode,
            copy_bundle=not dry_run,
        )
        if dry_run:
            return PublishResult(plan=plan, dry_run=True, url=url)

        api = _hf_api(token)
        api.create_repo(
            repo_id=repo_id,
            repo_type="space",
            space_sdk=space_sdk,
            private=private,
            exist_ok=True,
        )
        if hardware:
            api.request_space_hardware(repo_id=repo_id, hardware=hardware)
        api.upload_folder(
            repo_id=repo_id,
            repo_type="space",
            folder_path=str(staging_dir),
            commit_message=commit_message or f"Publish HyperView {space_sdk} Space",
            delete_patterns=["*"],
        )
    return PublishResult(plan=plan, dry_run=False, url=url)


def _cloudflare_command(manifest: dict[str, Any]) -> list[str]:
    cloudflare = _manifest_section(_manifest_section(manifest, "deployment"), "cloudflare")
    command = cloudflare.get("command")
    if not isinstance(command, str) or not command.strip():
        raise RuntimeError(
            "The bundle manifest records no Cloudflare deploy command. Re-export the workspace "
            "with `hyperview export` to regenerate wrangler.jsonc and the command."
        )
    return shlex.split(command)


def _rewrite_worker_name(bundle_dir: Path, config_name: str, project: str) -> None:
    config_path = bundle_dir / config_name
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read the Wrangler configuration: {config_path}") from exc
    config["name"] = project
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


def _publish_to_cloudflare(
    bundle_dir: Path,
    manifest: dict[str, Any],
    *,
    project: str | None,
    dry_run: bool,
) -> PublishResult:
    command = _cloudflare_command(manifest)
    cloudflare = _manifest_section(_manifest_section(manifest, "deployment"), "cloudflare")
    config_name = str(cloudflare.get("config") or "wrangler.jsonc")
    worker_name = project or str(cloudflare.get("worker_name") or "")
    num_files, bundle_bytes = _bundle_stats(bundle_dir)
    notes: list[str] = []
    if project:
        notes.append(f"Rewrites {config_name} name to {project!r} before deploying.")
    plan = PublishPlan(
        target="cloudflare",
        mode="static",
        bundle_dir=bundle_dir,
        destination=worker_name,
        num_files=num_files,
        bundle_bytes=bundle_bytes,
        command=command,
        notes=tuple(notes),
    )
    if dry_run:
        return PublishResult(plan=plan, dry_run=True)

    executable = shutil.which(command[0])
    if executable is None:
        raise RuntimeError(
            f"{command[0]} is not on PATH, so the bundle cannot be deployed to Cloudflare. "
            "Install Node.js (which provides npx) and the Wrangler CLI, then rerun, or run "
            f"`{shlex.join(command)}` yourself from {bundle_dir}."
        )
    if project:
        _rewrite_worker_name(bundle_dir, config_name, project)
    try:
        subprocess.run(command, cwd=str(bundle_dir), check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"`{shlex.join(command)}` failed with exit code {exc.returncode} in {bundle_dir}."
        ) from exc
    return PublishResult(plan=plan, dry_run=False)


def _publish_to_dir(
    bundle_dir: Path,
    manifest: dict[str, Any],
    destination: str,
    *,
    dry_run: bool,
) -> PublishResult:
    out_dir = Path(destination).expanduser().resolve()
    num_files, bundle_bytes = _bundle_stats(bundle_dir)
    plan = PublishPlan(
        target="dir",
        mode="static",
        bundle_dir=bundle_dir,
        destination=str(out_dir),
        num_files=num_files,
        bundle_bytes=bundle_bytes,
    )
    if dry_run:
        return PublishResult(plan=plan, dry_run=True, output_dir=out_dir)
    result = copy_static_bundle(bundle_dir, out_dir)
    return PublishResult(plan=plan, dry_run=False, output_dir=result.output_dir)


def publish(
    bundle_dir: str | Path,
    to: str,
    *,
    mode: str = "static",
    private: bool = False,
    dry_run: bool = False,
    project: str | None = None,
    title: str | None = None,
    emoji: str | None = None,
    extra_pip: tuple[str, ...] | list[str] = (),
    hardware: str | None = None,
    commit_message: str | None = None,
    token: str | None = None,
) -> PublishResult:
    """Publish an exported HyperView bundle.

    Args:
        bundle_dir: A directory written by ``hyperview export``.
        to: ``hf:<owner>/<name>``, ``cloudflare``, or ``dir:<path>``.
        mode: ``static`` for a Static Space, ``live`` for a container that runs
            ``hyperview serve --from``. Hugging Face targets only.
        private: Create the Hugging Face Space private.
        dry_run: Render and return the plan without touching the network or any
            directory other than a temporary staging one.
        project: Cloudflare Worker name, overriding the one in the manifest.
        title: Space title, overriding the one derived from the manifest.
        emoji: Space emoji, overriding the default.
        extra_pip: Additional ``pkg==version`` requirements for a Live Space.
        hardware: Hugging Face hardware flavor to request, such as ``cpu-upgrade``.
        commit_message: Commit message for the Hugging Face upload.
        token: Hugging Face token; falls back to ``HF_TOKEN`` and the local login.
    """

    resolved_bundle, manifest = _load_bundle(bundle_dir)
    kind, destination = parse_target(to)
    extras = tuple(extra_pip or ())

    if kind == "hf":
        return _publish_to_hf(
            resolved_bundle,
            manifest,
            destination,
            mode=mode,
            private=private,
            dry_run=dry_run,
            title=title,
            emoji=emoji,
            extra_pip=extras,
            hardware=hardware,
            commit_message=commit_message,
            token=token,
        )
    if mode != "static":
        raise ValueError(f"--mode {mode} applies to Hugging Face targets only, not {kind}.")
    if kind == "cloudflare":
        return _publish_to_cloudflare(
            resolved_bundle,
            manifest,
            project=project,
            dry_run=dry_run,
        )
    return _publish_to_dir(resolved_bundle, manifest, destination, dry_run=dry_run)
