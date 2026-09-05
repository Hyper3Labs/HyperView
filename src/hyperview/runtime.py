"""Runtime, provider registry, and workspace state for HyperView."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import json
import os
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from filelock import FileLock

from hyperview.core.dataset import Dataset
from hyperview.extensions import (
    ExtensionManifest,
    LoadedExtension,
    load_core_panel_definitions,
    load_extension_tools,
    resolve_panel_source,
    resolve_shipped_extension,
    unload_extension_modules,
)
from hyperview.panel_definitions import (
    PanelDefinition,
    merge_default_props,
    validate_json_contract,
)
from hyperview.storage.config import StorageConfig, get_default_home_dir
from hyperview.storage.schema import (
    index_id_for_space_key,
    parse_layout_dimension,
    space_key_from_index_ref,
)
from hyperview.tools import RunContext, ToolRegistry


def _now_ts() -> int:
    return int(time.time())


def _positive_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _panel_layout_fields(
    default_layout: dict[str, Any] | None,
    *,
    position: str | None,
    reference_panel_id: str | None,
    direction: str | None,
    width: int | None,
    height: int | None,
    min_width: int | None,
    min_height: int | None,
    max_width: int | None,
    max_height: int | None,
    fallback_position: str = "right",
) -> dict[str, Any]:
    layout = dict(default_layout or {})
    resolved_position = str(position or layout.get("position") or fallback_position)
    if resolved_position not in {"center", "right", "bottom"}:
        raise ValueError("position must be one of center, right, bottom")
    resolved_direction = direction or _str_or_none(layout.get("direction"))
    if resolved_direction is not None and resolved_direction not in {
        "right",
        "left",
        "above",
        "below",
        "within",
    }:
        raise ValueError("direction must be one of right, left, above, below, within")

    def dimension(arg_value: int | None, layout_key: str) -> int | None:
        return _positive_int_or_none(
            arg_value if arg_value is not None else layout.get(layout_key)
        )

    return {
        "position": resolved_position,
        "reference_panel_id": reference_panel_id
        if reference_panel_id is not None
        else _str_or_none(layout.get("reference_panel_id")),
        "direction": resolved_direction,
        "width": dimension(width, "width"),
        "height": dimension(height, "height"),
        "min_width": dimension(min_width, "min_width"),
        "min_height": dimension(min_height, "min_height"),
        "max_width": dimension(max_width, "max_width"),
        "max_height": dimension(max_height, "max_height"),
    }


_UNSET = object()
SAMPLES_PANEL_STATE_ID = "samples"
SAMPLES_PANEL_STATE_ALIASES = {SAMPLES_PANEL_STATE_ID, "grid"}
RESERVED_PANEL_STATE_IDS = {SAMPLES_PANEL_STATE_ID}


def _stable_collection_id(kind: str, query: dict[str, Any]) -> str:
    payload = json.dumps(query, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{kind}:{digest}"


def _json_object_copy(value: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy and reject non-serializable state early."""

    return json.loads(json.dumps(value))


def _atomic_write_json(path: Path, payload: dict[str, Any], *, default: Any = None) -> None:
    """Replace registry JSON without exposing a truncated intermediate file."""

    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=default),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_merge_patch(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply RFC 7396-style merge patch semantics to panel state."""

    result = _json_object_copy(current)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _json_merge_patch(result[key], value)
            continue
        result[key] = json.loads(json.dumps(value))
    return result


def get_runtime_config_dir() -> Path:
    """Where the workspace, provider, and job registries live.

    ``HYPERVIEW_HOME`` when set. Otherwise the parent of the datasets
    directory, which is ``~/.hyperview`` by default -- and, when only
    ``HYPERVIEW_DATASETS_DIR`` is set, whatever directory contains it. Two
    datasets directories with the same parent therefore share one registry;
    set ``HYPERVIEW_HOME`` to keep a run fully separate.
    """

    if os.environ.get("HYPERVIEW_HOME"):
        config_dir = get_default_home_dir()
    else:
        config_dir = StorageConfig.default().datasets_dir.parent
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_provider_registry_path() -> Path:
    return get_runtime_config_dir() / "providers.json"


def get_workspace_registry_path() -> Path:
    return get_runtime_config_dir() / "workspaces.json"


def get_job_registry_path() -> Path:
    return get_runtime_config_dir() / "jobs.json"


def _parse_import_path(import_path: str) -> tuple[str, str]:
    if ":" not in import_path:
        raise ValueError(f"import_path must use the form '<module>:<object>', got '{import_path}'")

    module_name, object_name = import_path.split(":", 1)
    if not module_name or not object_name:
        raise ValueError(f"import_path must use the form '<module>:<object>', got '{import_path}'")
    return module_name, object_name


def _import_from_path(import_path: str) -> Any:
    module_name, object_name = _parse_import_path(import_path)
    module = importlib.import_module(module_name)

    try:
        return getattr(module, object_name)
    except AttributeError as exc:
        raise ValueError(f"Object '{object_name}' not found in module '{module_name}'") from exc


@dataclass
class ProviderRegistration:
    alias: str
    kind: Literal["python"]
    import_path: str
    description: str | None = None
    defaults: dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=_now_ts)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderRegistration:
        return cls(
            alias=str(data["alias"]),
            kind="python",
            import_path=str(data["import_path"]),
            description=data.get("description"),
            defaults=dict(data.get("defaults") or {}),
            created_at=int(data.get("created_at") or _now_ts()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def identity(self) -> str:
        """What this alias currently resolves to.

        Two registrations of the same alias are interchangeable only when they
        import the same target with the same defaults. Callers that cache
        instantiated providers key on this so re-registering an alias replaces
        the cached instance instead of being ignored.
        """

        payload = json.dumps(
            {"import_path": self.import_path, "defaults": self.defaults},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ProviderRegistry:
    """Persistent registry for user-defined embedding providers."""

    def __init__(self, path: Path | None = None):
        self.path = path or get_provider_registry_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._providers: dict[str, ProviderRegistration] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._providers = {}
            return

        data = json.loads(self.path.read_text())
        providers = data.get("providers") or []
        self._providers = {
            entry["alias"]: ProviderRegistration.from_dict(entry) for entry in providers
        }

    def _save(self) -> None:
        payload = {
            "providers": [
                provider.to_dict()
                for provider in sorted(self._providers.values(), key=lambda item: item.alias)
            ]
        }
        _atomic_write_json(self.path, payload)

    def list(self) -> list[ProviderRegistration]:
        return [self._providers[key] for key in sorted(self._providers)]

    def get(self, alias: str) -> ProviderRegistration | None:
        return self._providers.get(alias)

    def register_python(
        self,
        alias: str,
        import_path: str,
        *,
        description: str | None = None,
        defaults: dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> ProviderRegistration:
        alias = alias.strip()
        if not alias:
            raise ValueError("alias must be a non-empty string")

        existing = self._providers.get(alias)
        if existing is not None and not overwrite:
            raise ValueError(f"Provider alias already registered: {alias}")

        _parse_import_path(import_path)

        registration = ProviderRegistration(
            alias=alias,
            kind="python",
            import_path=import_path,
            description=description,
            defaults=dict(defaults or {}),
        )
        self._providers[alias] = registration
        self._save()
        return registration

    def unregister(self, alias: str) -> bool:
        removed = self._providers.pop(alias, None)
        if removed is None:
            return False
        self._save()
        return True

    def is_available(self, alias: str) -> bool:
        registration = self.get(alias)
        if registration is None:
            return False
        try:
            _import_from_path(registration.import_path)
        except Exception:
            return False
        return True

    def instantiate(self, alias: str, **kwargs: Any) -> Any:
        registration = self.get(alias)
        if registration is None:
            raise ValueError(f"Unknown custom provider alias: {alias}")

        target = _import_from_path(registration.import_path)
        resolved_kwargs = {**registration.defaults, **kwargs}

        if inspect.isclass(target):
            return target(**resolved_kwargs)

        if callable(target):
            created = target(**resolved_kwargs)
            return created

        if resolved_kwargs:
            raise ValueError(
                f"Custom provider '{alias}' resolved to a non-callable object and cannot accept kwargs"
            )
        return target


LEGACY_PANEL_KINDS = ("builtin", "extension", "module", "scatter")


def _panel_text_field(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def migrate_legacy_panel_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Fold a legacy panel ``kind`` into the fields it implied, and drop it.

    ``kind`` used to be four disagreeing enums over the same panel. It is gone
    from :class:`PanelInstance` and from every payload the runtime writes; what
    it decided is read off ``renderer``, ``builtin_panel``, ``module_file`` and
    ``panel_type`` instead. Payloads written before that -- a persisted
    ``workspaces.json``, an exported bundle, a `workspace.panel.add` request
    from an older script -- still carry it, so this is the one place that knows
    what each legacy value meant. The returned payload never contains ``kind``.
    """

    payload = dict(data)
    raw_kind = payload.pop("kind", None)
    if raw_kind is None:
        return payload

    kind = str(raw_kind).strip()
    if kind not in LEGACY_PANEL_KINDS:
        raise ValueError(
            f"Unsupported panel kind '{kind}'; expected one of: "
            + ", ".join(LEGACY_PANEL_KINDS)
        )

    if kind in {"builtin", "scatter"}:
        default_native = "scatter" if kind == "scatter" else "builtin"
        native = (
            _panel_text_field(payload, "builtin_panel")
            or _panel_text_field(payload, "panel_type")
            or default_native
        )
        payload["builtin_panel"] = native
        if kind == "scatter":
            payload["panel_type"] = _panel_text_field(payload, "panel_type") or "scatter"
        payload["renderer"] = _panel_text_field(payload, "renderer") or f"native:{native}"
        source = _panel_text_field(payload, "source")
        payload["source"] = "shipped" if source in {None, "builtin"} else source

    # ``module`` and ``extension`` implied nothing that ``renderer``,
    # ``module_file`` and ``extension``/``extension_panel`` do not already say.
    return payload


def panel_payload_renders_module(data: dict[str, Any]) -> bool:
    """Whether a raw panel payload -- legacy or current -- is drawn by a module.

    The runtime answers this from a parsed :class:`PanelInstance`; callers that
    still hold the untyped payload (bundle restore, before the module path has
    been repaired) get the same answer here.
    """

    payload = migrate_legacy_panel_payload(data)
    renderer = _panel_text_field(payload, "renderer")
    if renderer is not None:
        return not renderer.startswith("native:")
    if _panel_text_field(payload, "module_file") is not None:
        return True
    return _panel_text_field(payload, "builtin_panel") is None


def _native_component_name(renderer: str | None) -> str | None:
    """The frontend component a ``native:`` renderer reference names."""

    if not renderer or not renderer.startswith("native:"):
        return None
    return renderer.removeprefix("native:").strip() or None


@dataclass
class PanelInstance:
    """A placed panel: what a workspace shows, where, and how it is drawn.

    There is no ``kind``. The renderer namespace decides rendering -- a
    ``native:`` renderer resolves to a component the shell bundles, a
    ``module:`` renderer is loaded as an ESM module -- and the panel type,
    provenance and renderer are all derivable from the fields that name the
    panel itself. :func:`migrate_legacy_panel_payload` translates payloads
    written before that.
    """

    id: str
    title: str
    module_file: str | None = None
    panel_type: str | None = None
    source: str | None = None
    renderer: str | None = None
    builtin_panel: str | None = None
    extension: str | None = None
    extension_panel: str | None = None
    position: Literal["center", "right", "bottom"] = "right"
    layout_key: str | None = None
    geometry: str | None = None
    layout_dimension: int | None = None
    reference_panel_id: str | None = None
    direction: Literal["right", "left", "above", "below", "within"] | None = None
    width: int | None = None
    height: int | None = None
    min_width: int | None = None
    min_height: int | None = None
    max_width: int | None = None
    max_height: int | None = None
    visible: bool = True
    active: bool = False
    props: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.renderer is None:
            if self.builtin_panel:
                self.renderer = f"native:{self.builtin_panel}"
            elif self.module_file:
                self.renderer = f"module:{Path(self.module_file).name}"
        if self.renders_native() and self.source in {None, "builtin"}:
            self.source = "shipped"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PanelInstance:
        data = migrate_legacy_panel_payload(data)

        builtin_panel = data.get("builtin_panel")
        if builtin_panel is not None:
            builtin_panel = str(builtin_panel).strip() or None

        position = str(data.get("position") or "right")
        if position not in {"center", "right", "bottom"}:
            position = "right"

        direction = data.get("direction")
        if direction is not None:
            direction = str(direction)
            if direction not in {"right", "left", "above", "below", "within"}:
                direction = None

        layout_dimension = data.get("layout_dimension")
        if layout_dimension is not None:
            try:
                layout_dimension = int(layout_dimension)
            except (TypeError, ValueError):
                layout_dimension = None

        def positive_int(key: str) -> int | None:
            value = data.get(key)
            if value is None:
                return None
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return None
            return parsed if parsed > 0 else None

        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            module_file=data.get("module_file"),
            panel_type=data.get("panel_type"),
            source=data.get("source"),
            renderer=data.get("renderer"),
            builtin_panel=builtin_panel,  # type: ignore[arg-type]
            extension=data.get("extension"),
            extension_panel=data.get("extension_panel"),
            position=position,  # type: ignore[arg-type]
            layout_key=data.get("layout_key"),
            geometry=data.get("geometry"),
            layout_dimension=layout_dimension,
            reference_panel_id=data.get("reference_panel_id"),
            direction=direction,  # type: ignore[arg-type]
            width=positive_int("width"),
            height=positive_int("height"),
            min_width=positive_int("min_width"),
            min_height=positive_int("min_height"),
            max_width=positive_int("max_width"),
            max_height=positive_int("max_height"),
            visible=bool(data.get("visible", True)),
            active=bool(data.get("active", False)),
            props=dict(data.get("props") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """The wire form of this panel: what a browser is allowed to see.

        ``module_file`` is an absolute path on the machine running the runtime
        and has no meaning in a browser, so it is not part of the wire form.
        Anything that has to keep it -- the workspace registry on disk -- uses
        :meth:`to_storage_dict`.
        """

        payload = self.to_storage_dict()
        payload.pop("module_file", None)
        return payload

    def to_storage_dict(self) -> dict[str, Any]:
        """The wire form plus the host-only fields a reload needs back."""

        payload = asdict(self)
        payload["panel_type"] = self.resolved_panel_type()
        payload["source"] = self.resolved_source()
        payload["renderer"] = self.resolved_renderer()
        payload["layout"] = self.layout_dict()
        return payload

    def resolved_renderer(self) -> str:
        if self.renderer:
            return self.renderer
        if self.module_file:
            return f"module:{Path(self.module_file).name}"
        if self.builtin_panel:
            return f"native:{self.builtin_panel}"
        return "module:unknown"

    def renders_module(self) -> bool:
        """Whether this panel is drawn by loading its panel module."""

        return not self.resolved_renderer().startswith("native:")

    def renders_native(self) -> bool:
        """Whether this panel is drawn by a component the shell bundles."""

        return not self.renders_module()

    def resolved_panel_type(self) -> str:
        if self.panel_type:
            return self.panel_type
        if self.renders_native():
            return self.builtin_panel or "builtin"
        if self.extension and self.extension_panel:
            return f"{self.extension}.{self.extension_panel}"
        return "module"

    def resolved_source(self) -> str:
        if self.source:
            return self.source
        if self.renders_native():
            return "shipped"
        if self.extension:
            return "extension"
        return "module"

    def layout_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "reference_panel_id": self.reference_panel_id,
            "direction": self.direction,
            "width": self.width,
            "height": self.height,
            "min_width": self.min_width,
            "min_height": self.min_height,
            "max_width": self.max_width,
            "max_height": self.max_height,
        }

    def resolved_module_file(self) -> Path | None:
        if not self.module_file:
            return None
        return Path(self.module_file).expanduser().resolve()


#: The name a placed panel had before D4. Kept so external code and the public
#: ``hyperview`` API keep importing; :class:`PanelInstance` is the name.
CustomPanelSpec = PanelInstance


def _ensure_unique_panel_ids(panels: list[PanelInstance]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for panel in panels:
        if panel.id in seen and panel.id not in duplicates:
            duplicates.append(panel.id)
        seen.add(panel.id)
    if duplicates:
        duplicate_list = ", ".join(repr(panel_id) for panel_id in duplicates)
        raise ValueError(
            f"Custom panel ids must be unique. Duplicate panel id(s): {duplicate_list}."
        )


@dataclass
class LayoutViewState:
    camera_3d: dict[str, float] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayoutViewState:
        camera_raw = data.get("camera_3d")
        camera_3d: dict[str, float] | None = None
        if isinstance(camera_raw, dict):
            parsed: dict[str, float] = {}
            required_keys = (
                "yaw",
                "pitch",
                "distance",
                "target_x",
                "target_y",
                "target_z",
                "ortho_scale",
            )
            for key in required_keys:
                value = camera_raw.get(key)
                if value is None:
                    parsed = {}
                    break
                try:
                    parsed[key] = float(value)
                except (TypeError, ValueError):
                    parsed = {}
                    break
            if len(parsed) == len(required_keys):
                camera_3d = parsed
        return cls(camera_3d=camera_3d)

    def to_dict(self) -> dict[str, Any]:
        return {"camera_3d": dict(self.camera_3d) if self.camera_3d is not None else None}


@dataclass
class SimilarityQueryState:
    anchor_sample_id: str | None = None
    query_text: str | None = None
    layout_key: str | None = None
    space_key: str | None = None
    k: int = 18
    source: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimilarityQueryState | None:
        anchor_sample_id = str(data.get("anchor_sample_id") or "").strip() or None
        query_text = str(data.get("query_text") or "").strip() or None
        if not anchor_sample_id and not query_text:
            return None
        try:
            k = int(data.get("k") or 18)
        except (TypeError, ValueError):
            k = 18
        return cls(
            anchor_sample_id=anchor_sample_id,
            query_text=query_text,
            layout_key=data.get("layout_key"),
            space_key=data.get("space_key")
            or space_key_from_index_ref(data.get("index_id")),
            k=max(1, min(k, 100)),
            source=data.get("source"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "layout_key": self.layout_key,
            "index_id": index_id_for_space_key(self.space_key) if self.space_key else None,
            "space_key": self.space_key,
            "k": self.k,
            "source": self.source,
        }
        if self.anchor_sample_id:
            payload["anchor_sample_id"] = self.anchor_sample_id
        if self.query_text:
            payload["query_text"] = self.query_text
        return payload


@dataclass
class EntityRef:
    dataset_id: str
    entity_set_id: str
    entity_id: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityRef:
        return cls(
            dataset_id=str(data.get("datasetId") or data.get("dataset_id") or ""),
            entity_set_id=str(data.get("entitySetId") or data.get("entity_set_id") or "samples"),
            entity_id=str(data.get("entityId") or data.get("entity_id") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasetId": self.dataset_id,
            "entitySetId": self.entity_set_id,
            "entityId": self.entity_id,
        }


@dataclass
class CollectionState:
    id: str
    dataset_id: str
    entity_set_id: str = "samples"
    kind: Literal[
        "all",
        "filter",
        "selection",
        "neighbors",
        "lasso",
        "search",
        "tool_result",
        "extension",
    ] = "all"
    query: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] | None = None
    created_at: int = field(default_factory=_now_ts)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CollectionState:
        kind = str(data.get("kind") or "all")
        if kind not in {
            "all",
            "filter",
            "selection",
            "neighbors",
            "lasso",
            "search",
            "tool_result",
            "extension",
        }:
            kind = "extension"

        scores: dict[str, float] | None = None
        raw_scores = data.get("scores")
        if isinstance(raw_scores, dict):
            scores = {}
            for key, value in raw_scores.items():
                try:
                    scores[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue

        return cls(
            id=str(data["id"]),
            dataset_id=str(data.get("dataset_id") or data.get("datasetId") or ""),
            entity_set_id=str(data.get("entity_set_id") or data.get("entitySetId") or "samples"),
            kind=kind,  # type: ignore[arg-type]
            query=dict(data.get("query") or {}),
            scores=scores,
            created_at=int(data.get("created_at") or data.get("createdAt") or _now_ts()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "entity_set_id": self.entity_set_id,
            "kind": self.kind,
            "query": _json_object_copy(self.query),
            "scores": dict(self.scores) if self.scores is not None else None,
            "created_at": self.created_at,
        }


@dataclass
class PanelStateEntry:
    state: dict[str, Any] = field(default_factory=dict)
    state_revision: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PanelStateEntry:
        raw_state = data.get("state") if isinstance(data, dict) else None
        state = raw_state if isinstance(raw_state, dict) else {}
        try:
            state_revision = int(data.get("state_revision") or 0)
        except (TypeError, ValueError):
            state_revision = 0
        return cls(
            state=_json_object_copy(state),
            state_revision=max(0, state_revision),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": _json_object_copy(self.state),
            "state_revision": self.state_revision,
        }


def _authored_collection_id(panel: PanelInstance) -> str | None:
    """The collection a view authored for a Samples panel, if any."""

    authored = panel.props.get("collectionId", panel.props.get("collection_id"))
    if isinstance(authored, str) and authored.strip():
        return authored.strip()
    return None


def _samples_collection_state(collection: CollectionState) -> dict[str, Any]:
    return {
        "collection_id": collection.id,
        "collection": collection.to_dict(),
    }


def _samples_filter_state(collection: CollectionState) -> dict[str, Any]:
    return {
        "mode": "collection",
        "retrieval": None,
        **_samples_collection_state(collection),
    }


def _samples_selection_state(
    collection: CollectionState,
    *,
    focus: bool,
    state_revision: int,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "mode": "collection",
        "retrieval": None,
        **_samples_collection_state(collection),
    }
    if focus:
        state["focus_request"] = {
            "kind": "selection",
            "collection_id": collection.id,
            "revision": state_revision,
        }
    else:
        state["focus_request"] = None
    return state


def _samples_retrieval_state(
    query: SimilarityQueryState,
    collection: CollectionState | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "mode": "retrieval",
        "retrieval": query.to_dict(),
    }
    if collection is not None:
        state.update(_samples_collection_state(collection))
    return state


def _clear_samples_collection_state_patch() -> dict[str, Any]:
    return {
        "collection_id": None,
        "collection": None,
    }


def _samples_panel_collection_kind(state: dict[str, Any]) -> str | None:
    collection = state.get("collection")
    if not isinstance(collection, dict):
        return None
    kind = collection.get("kind")
    return kind if isinstance(kind, str) else None


def _samples_panel_retrieval_query(
    panels: dict[str, PanelStateEntry],
    panel_id: str = SAMPLES_PANEL_STATE_ID,
) -> SimilarityQueryState | None:
    state_entry = panels.get(panel_id)
    retrieval = state_entry.state.get("retrieval") if state_entry is not None else None
    if not isinstance(retrieval, dict):
        return None
    return SimilarityQueryState.from_dict(retrieval)


def _custom_panel_instance_payload(
    panel: PanelInstance,
    panel_states: dict[str, PanelStateEntry],
    *,
    data: dict[str, Any] | None = None,
    for_storage: bool = False,
) -> dict[str, Any]:
    spec = panel.to_storage_dict() if for_storage else panel.to_dict()
    payload = {
        **spec,
        "state_revision": panel_states.get(panel.id, PanelStateEntry()).state_revision,
    }
    if data is not None:
        payload["data"] = data
    return payload


@dataclass
class WorkspaceUiState:
    active_layout_key: str | None = None
    selected_ids: list[str] = field(default_factory=list)
    custom_panels: list[PanelInstance] = field(default_factory=list)
    panels: dict[str, PanelStateEntry] = field(default_factory=dict)
    has_explicit_view: bool = False
    active_panel_id: str | None = None
    layout_views: dict[str, LayoutViewState] = field(default_factory=dict)
    layout: dict[str, Any] | None = None
    layout_revision: int = 0
    view_revision: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceUiState:
        custom_panels: list[PanelInstance] = []
        for entry in list(data.get("custom_panels") or []):
            panel = PanelInstance.from_dict(entry)
            if panel.renders_native() or panel.module_file:
                custom_panels.append(panel)

        layout_views: dict[str, LayoutViewState] = {}
        raw_layout_views = data.get("layout_views") or {}
        if isinstance(raw_layout_views, dict):
            for layout_key, view_data in raw_layout_views.items():
                if isinstance(layout_key, str) and isinstance(view_data, dict):
                    layout_views[layout_key] = LayoutViewState.from_dict(view_data)

        panels: dict[str, PanelStateEntry] = {}
        raw_panels = data.get("panels") or {}
        if isinstance(raw_panels, dict):
            for panel_id, panel_data in raw_panels.items():
                if isinstance(panel_id, str) and isinstance(panel_data, dict):
                    panels[panel_id] = PanelStateEntry.from_dict(panel_data)

        for entry in list(data.get("custom_panels") or []):
            if not isinstance(entry, dict) or "state" not in entry:
                continue
            panel_id = str(entry.get("id") or "").strip()
            if not panel_id or panel_id in panels:
                continue
            panels[panel_id] = PanelStateEntry.from_dict(entry)

        selected_ids = list(data.get("selected_ids") or [])
        active_retrieval = _samples_panel_retrieval_query(panels)
        if active_retrieval is not None:
            selected_ids = []

        return cls(
            active_layout_key=data.get("active_layout_key"),
            selected_ids=selected_ids,
            custom_panels=custom_panels,
            panels=panels,
            has_explicit_view=bool(data.get("has_explicit_view", False)),
            active_panel_id=data.get("active_panel_id"),
            layout_views=layout_views,
            layout=(
                _json_object_copy(data["layout"])
                if isinstance(data.get("layout"), dict)
                else None
            ),
            layout_revision=max(0, int(data.get("layout_revision") or 0)),
            view_revision=int(data.get("view_revision") or 0),
        )

    def to_dict(self, *, for_storage: bool = False) -> dict[str, Any]:
        return {
            "active_layout_key": self.active_layout_key,
            "selected_ids": list(self.selected_ids),
            "custom_panels": [
                _custom_panel_instance_payload(panel, self.panels, for_storage=for_storage)
                for panel in self.custom_panels
            ],
            "panels": {
                panel_id: state.to_dict() for panel_id, state in sorted(self.panels.items())
            },
            "has_explicit_view": self.has_explicit_view,
            "active_panel_id": self.active_panel_id,
            "layout_views": {
                layout_key: view.to_dict() for layout_key, view in sorted(self.layout_views.items())
            },
            "layout": _json_object_copy(self.layout) if self.layout is not None else None,
            "layout_revision": self.layout_revision,
            "view_revision": self.view_revision,
        }


@dataclass
class WorkspaceState:
    id: str
    dataset_name: str | None = None
    collections: dict[str, CollectionState] = field(default_factory=dict)
    ui: WorkspaceUiState = field(default_factory=WorkspaceUiState)
    created_at: int = field(default_factory=_now_ts)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceState:
        collections: dict[str, CollectionState] = {}
        raw_collections = data.get("collections") or []
        if isinstance(raw_collections, dict):
            raw_collections = raw_collections.values()
        for entry in list(raw_collections):
            if not isinstance(entry, dict) or "id" not in entry:
                continue
            collection = CollectionState.from_dict(entry)
            collections[collection.id] = collection

        return cls(
            id=str(data["id"]),
            dataset_name=data.get("dataset_name"),
            collections=collections,
            ui=WorkspaceUiState.from_dict(data.get("ui") or {}),
            created_at=int(data.get("created_at") or _now_ts()),
        )

    def to_dict(self, *, for_storage: bool = False) -> dict[str, Any]:
        """Serialize this workspace.

        ``for_storage`` keeps the host-only panel fields (the absolute
        ``module_file`` path) that a reload needs to find a module panel's
        source again. Everything served to a browser leaves them out.
        """

        return {
            "id": self.id,
            "dataset_name": self.dataset_name,
            "collections": [
                collection.to_dict()
                for collection in sorted(self.collections.values(), key=lambda item: item.id)
            ],
            "ui": self.ui.to_dict(for_storage=for_storage),
            "created_at": self.created_at,
        }


class WorkspaceRegistry:
    """Persistent registry for HyperView workspaces."""

    def __init__(self, path: Path | None = None):
        self.path = path or get_workspace_registry_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.active_workspace_id: str | None = None
        self._workspaces: dict[str, WorkspaceState] = {}
        self._load()
        if not self._workspaces:
            self.create_workspace("default", activate=True)

    def _load(self) -> None:
        if not self.path.exists():
            self.active_workspace_id = None
            self._workspaces = {}
            return

        data = json.loads(self.path.read_text())
        self.active_workspace_id = data.get("active_workspace_id")
        self._workspaces = {
            entry["id"]: WorkspaceState.from_dict(entry)
            for entry in list(data.get("workspaces") or [])
        }

    def _save(
        self,
        *,
        changed_workspace_ids: set[str] | None = None,
        deleted_workspace_ids: set[str] | None = None,
    ) -> None:
        """Persist workspace changes without clobbering sibling runtimes.

        Multiple HyperView Spaces commonly run as separate processes while sharing
        the default registry. Each process has an in-memory snapshot, so rewriting
        every workspace would restore stale copies of workspaces owned by the other
        processes. Merge only the workspaces changed by this registry while holding
        an inter-process lock.
        """

        changed_ids = set(self._workspaces) if changed_workspace_ids is None else set(changed_workspace_ids)
        deleted_ids = set(deleted_workspace_ids or ())
        payload = {
            "active_workspace_id": self.active_workspace_id,
            "workspaces": [],
        }
        lock = FileLock(str(self.path) + ".lock")
        with lock:
            persisted: dict[str, WorkspaceState] = {}
            if self.path.exists():
                data = json.loads(self.path.read_text())
                persisted = {
                    entry["id"]: WorkspaceState.from_dict(entry)
                    for entry in list(data.get("workspaces") or [])
                }
            for workspace_id in deleted_ids:
                persisted.pop(workspace_id, None)
            for workspace_id in changed_ids:
                workspace = self._workspaces.get(workspace_id)
                if workspace is not None:
                    persisted[workspace_id] = workspace
            self._workspaces = persisted
            payload["workspaces"] = [
                workspace.to_dict(for_storage=True)
                for workspace in sorted(persisted.values(), key=lambda item: item.id)
            ]
            _atomic_write_json(self.path, payload)

    def list(self) -> list[WorkspaceState]:
        return [self._workspaces[key] for key in sorted(self._workspaces)]

    def get(self, workspace_id: str) -> WorkspaceState | None:
        return self._workspaces.get(workspace_id)

    def create_workspace(self, workspace_id: str, *, activate: bool = False) -> WorkspaceState:
        workspace_id = workspace_id.strip()
        if not workspace_id:
            raise ValueError("workspace_id must be a non-empty string")
        if workspace_id in self._workspaces:
            raise ValueError(f"Workspace already exists: {workspace_id}")

        workspace = WorkspaceState(id=workspace_id)
        self._workspaces[workspace_id] = workspace
        if activate or self.active_workspace_id is None:
            self.active_workspace_id = workspace_id
        self._save(changed_workspace_ids={workspace_id})
        return workspace

    def ensure_workspace(self, workspace_id: str, *, activate: bool = False) -> WorkspaceState:
        workspace = self.get(workspace_id)
        if workspace is not None:
            if activate:
                self.active_workspace_id = workspace_id
                self._save(changed_workspace_ids=set())
            return workspace

        return self.create_workspace(workspace_id, activate=activate)

    def set_active_workspace(self, workspace_id: str) -> WorkspaceState:
        workspace = self.get(workspace_id)
        if workspace is None:
            raise ValueError(f"Unknown workspace: {workspace_id}")
        self.active_workspace_id = workspace_id
        self._save(changed_workspace_ids=set())
        return workspace

    def delete_workspace(self, workspace_id: str) -> WorkspaceState | None:
        workspace = self.get(workspace_id)
        if workspace is None:
            raise ValueError(f"Unknown workspace: {workspace_id}")
        if len(self._workspaces) <= 1:
            raise ValueError("Cannot delete the last remaining workspace")

        del self._workspaces[workspace_id]

        if self.active_workspace_id == workspace_id:
            remaining_ids = sorted(self._workspaces)
            self.active_workspace_id = remaining_ids[0] if remaining_ids else None

        self._save(changed_workspace_ids=set(), deleted_workspace_ids={workspace_id})
        if self.active_workspace_id is None:
            return None
        return self._workspaces[self.active_workspace_id]

    def set_dataset(self, workspace_id: str, dataset_name: str) -> WorkspaceState:
        workspace = self.ensure_workspace(workspace_id)
        workspace.dataset_name = dataset_name
        self._save(changed_workspace_ids={workspace_id})
        return workspace

    def update_workspace(self, workspace: WorkspaceState) -> None:
        self._workspaces[workspace.id] = workspace
        self._save(changed_workspace_ids={workspace.id})


@dataclass
class JobState:
    id: str
    kind: str
    workspace_id: str
    dataset_name: str | None
    status: Literal[
        "queued",
        "running",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    ] = "queued"
    created_at: int = field(default_factory=_now_ts)
    started_at: int | None = None
    finished_at: int | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    cancellation_requested: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobState:
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            workspace_id=str(data["workspace_id"]),
            dataset_name=data.get("dataset_name"),
            status=data.get("status", "queued"),
            created_at=int(data.get("created_at") or _now_ts()),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            result=data.get("result"),
            error=data.get("error"),
            params=dict(data.get("params") or {}),
            cancellation_requested=bool(data.get("cancellation_requested", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobRegistry:
    """Persistent registry for inspectable background job records."""

    def __init__(self, path: Path | None = None):
        self.path = path or get_job_registry_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, JobState] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._jobs = {}
            return

        data = json.loads(self.path.read_text())
        self._jobs = {
            entry["id"]: JobState.from_dict(entry)
            for entry in list(data.get("jobs") or [])
        }
        interrupted = False
        for job in self._jobs.values():
            if job.status not in {"queued", "running"}:
                continue
            job.status = "interrupted"
            job.finished_at = _now_ts()
            job.error = "Job was interrupted when the previous runtime stopped."
            interrupted = True
        if interrupted:
            self._save()

    def _save(self) -> None:
        payload = {
            "jobs": [
                job.to_dict()
                for job in sorted(self._jobs.values(), key=lambda item: item.id)
            ]
        }
        _atomic_write_json(self.path, payload, default=str)

    def list(self) -> list[JobState]:
        return [self._jobs[key] for key in sorted(self._jobs)]

    def get(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def update(self, job: JobState) -> None:
        self._jobs[job.id] = job
        self._save()


class _JobCancelledError(Exception):
    """Internal cooperative-cancellation signal for a running job."""


@dataclass(frozen=True)
class PanelTypeMatch:
    """A registered panel type, and the extension that contributed it."""

    definition: PanelDefinition
    extension: str | None = None
    extension_panel: str | None = None


@dataclass
class ExtensionInstallation:
    """Bookkeeping for an installed extension (in-memory, per-process)."""

    manifest: ExtensionManifest
    loaded: LoadedExtension
    workspace_id: str
    source: Literal["extension", "shipped"] = "extension"
    panel_ids: list[str] = field(default_factory=list)
    add_panels: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.manifest.name,
            "folder": str(self.manifest.folder),
            "description": self.manifest.description,
            "workspace_id": self.workspace_id,
            "source": self.source,
            "panels": list(self.panel_ids),
            "panel_definitions": [
                panel.to_definition(self.manifest.name, source=self.source).to_dict()
                for panel in self.manifest.panels
            ],
            "tools": [record.to_dict() for record in self.loaded.tools],
        }


class HyperViewRuntime:
    """Mutable application runtime for multi-workspace HyperView sessions."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
        workspace_registry: WorkspaceRegistry | None = None,
        job_registry: JobRegistry | None = None,
    ):
        self.runtime_id = uuid.uuid4().hex
        self.provider_registry = provider_registry or ProviderRegistry()
        self.workspace_registry = workspace_registry or WorkspaceRegistry()
        self.job_registry = job_registry or JobRegistry(
            self.workspace_registry.path.with_name("jobs.json")
        )
        self.tools = ToolRegistry()
        self._core_panel_definitions = tuple(load_core_panel_definitions())
        self._extensions: dict[str, ExtensionInstallation] = {}
        self._dataset_cache: dict[str, Dataset] = {}
        self._panel_module_revisions: dict[tuple[str, str, str], str] = {}
        self._lock = threading.RLock()
        self._version = 1
        self._version_source_client_id: str | None = None
        self._version_waiters: set[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = set()
        self._job_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._job_cancel_events: dict[str, threading.Event] = {}
        self._job_worker_context = threading.local()
        self._job_worker = threading.Thread(
            target=self._job_worker_loop,
            name="hyperview-job-worker",
            daemon=True,
        )
        self._job_worker.start()

    @property
    def version(self) -> int:
        return self._version

    @property
    def version_source_client_id(self) -> str | None:
        return self._version_source_client_id

    def _bump_version(self, *, source_client_id: str | None = None) -> None:
        with self._lock:
            self._version += 1
            self._version_source_client_id = source_client_id
            waiters = tuple(self._version_waiters)
        for loop, event in waiters:
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                # A disconnected SSE client may have already closed its event loop.
                continue

    async def wait_for_version(
        self,
        after_version: int,
        *,
        timeout: float | None = None,
    ) -> int | None:
        """Wait without polling until the runtime version advances."""

        loop = asyncio.get_running_loop()
        event = asyncio.Event()
        waiter = (loop, event)
        with self._lock:
            if self._version > after_version:
                return self._version
            self._version_waiters.add(waiter)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:  # noqa: UP041 — builtin TimeoutError only aliases this on 3.11+
            return None
        finally:
            with self._lock:
                self._version_waiters.discard(waiter)
        with self._lock:
            return self._version

    def _panel_module_revision(self, panel: PanelInstance) -> str | None:
        module_file = panel.resolved_module_file()
        if module_file is None:
            return None
        try:
            return hashlib.sha256(module_file.read_bytes()).hexdigest()[:16]
        except OSError:
            return "missing"

    def _sync_panel_module_revisions_locked(self) -> None:
        changed = False
        seen: set[tuple[str, str, str]] = set()

        for workspace in self.workspace_registry.list():
            for panel in workspace.ui.custom_panels:
                module_file = panel.resolved_module_file()
                if module_file is None:
                    continue

                key = (workspace.id, panel.id, str(module_file))
                revision = self._panel_module_revision(panel)
                if revision is None:
                    continue

                seen.add(key)
                previous = self._panel_module_revisions.get(key)
                self._panel_module_revisions[key] = revision
                if previous is not None and previous != revision:
                    changed = True

        for key in list(self._panel_module_revisions):
            if key not in seen:
                del self._panel_module_revisions[key]

        if changed:
            self._bump_version()

    def list_available_datasets(self) -> list[str]:
        datasets_dir = StorageConfig.default().datasets_dir
        datasets_dir.mkdir(parents=True, exist_ok=True)
        return sorted([path.name for path in datasets_dir.iterdir() if path.is_dir()])

    def attach_dataset_instance(
        self,
        workspace_id: str,
        dataset: Dataset,
        *,
        activate_workspace: bool = True,
    ) -> None:
        with self._lock:
            previous_workspace = self.workspace_registry.get(workspace_id)
            previous_dataset_name = (
                previous_workspace.dataset_name if previous_workspace is not None else None
            )
            self._dataset_cache[dataset.name] = dataset
            workspace = self.workspace_registry.set_dataset(workspace_id, dataset.name)
            if previous_dataset_name != dataset.name:
                workspace.ui.active_layout_key = None
                workspace.ui.selected_ids = []
                workspace.ui.panels = {}
                workspace.ui.layout_views = {}
                workspace.collections = {}
                for panel in workspace.ui.custom_panels:
                    self._seed_default_panel_state_locked(workspace, panel)
                self.workspace_registry.update_workspace(workspace)
            if activate_workspace:
                self.workspace_registry.set_active_workspace(workspace_id)
            self._bump_version()

    def create_workspace(self, workspace_id: str, *, activate: bool = False) -> WorkspaceState:
        with self._lock:
            workspace = self.workspace_registry.create_workspace(workspace_id, activate=activate)
            self._bump_version()
            return workspace

    def delete_workspace(self, workspace_id: str) -> WorkspaceState | None:
        with self._lock:
            workspace = self.workspace_registry.delete_workspace(workspace_id)
            self._bump_version()
            return workspace

    def set_active_workspace(self, workspace_id: str) -> WorkspaceState:
        with self._lock:
            workspace = self.workspace_registry.set_active_workspace(workspace_id)
            self._bump_version()
            return workspace

    def set_workspace_dataset(
        self,
        workspace_id: str,
        dataset_name: str,
    ) -> WorkspaceState:
        with self._lock:
            previous_workspace = self.workspace_registry.get(workspace_id)
            previous_dataset_name = (
                previous_workspace.dataset_name if previous_workspace is not None else None
            )
            workspace = self.workspace_registry.set_dataset(workspace_id, dataset_name)
            if previous_dataset_name != dataset_name:
                workspace.ui.active_layout_key = None
                workspace.ui.selected_ids = []
                workspace.ui.panels = {}
                workspace.ui.layout_views = {}
                workspace.collections = {}
                for panel in workspace.ui.custom_panels:
                    self._seed_default_panel_state_locked(workspace, panel)
                self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def restore_workspace_state(
        self,
        workspace_id: str,
        payload: dict[str, Any],
    ) -> WorkspaceState:
        """Replace a workspace's collections, view, and panel state wholesale.

        Restoring a bundle has to land the exported view exactly as it was:
        the same collection ids, the same panel instances and props, the same
        panel state and revisions, the same active layout key. Replaying that
        through the individual mutation commands would regenerate ids and
        revisions instead of reproducing them, so the payload -- shaped like
        the ``workspace`` section of :meth:`snapshot` -- is applied directly.
        """

        with self._lock:
            existing = self.workspace_registry.ensure_workspace(workspace_id)
            restored = WorkspaceState.from_dict({**payload, "id": workspace_id})
            # The workspace row is older than any view now being applied to it.
            restored.created_at = existing.created_at
            _ensure_unique_panel_ids(restored.ui.custom_panels)
            self.workspace_registry.update_workspace(restored)
            self._bump_version()
            return restored

    def get_workspace(self, workspace_id: str | None = None) -> WorkspaceState:
        resolved_workspace_id = workspace_id or self.workspace_registry.active_workspace_id
        if resolved_workspace_id is None:
            raise ValueError("No active workspace")
        workspace = self.workspace_registry.get(resolved_workspace_id)
        if workspace is None:
            raise ValueError(f"Unknown workspace: {resolved_workspace_id}")
        return workspace

    def get_dataset(
        self, workspace_id: str | None = None, dataset_name: str | None = None
    ) -> Dataset:
        workspace = self.get_workspace(workspace_id)
        resolved_dataset_name = dataset_name or workspace.dataset_name
        if not resolved_dataset_name:
            raise ValueError(f"Workspace '{workspace.id}' has no active dataset")

        cached = self._dataset_cache.get(resolved_dataset_name)
        if cached is not None:
            return cached

        dataset = Dataset(resolved_dataset_name)
        self._dataset_cache[resolved_dataset_name] = dataset
        return dataset

    def _resolve_panel_state_id_locked(self, workspace: WorkspaceState, panel_id: str) -> str:
        requested_panel_id = panel_id.strip()
        if not requested_panel_id:
            raise ValueError("panel_id must be a non-empty string")

        custom_panel_ids = {panel.id for panel in workspace.ui.custom_panels}
        if requested_panel_id in custom_panel_ids:
            return requested_panel_id
        if requested_panel_id in SAMPLES_PANEL_STATE_ALIASES:
            return SAMPLES_PANEL_STATE_ID
        raise KeyError(f"Panel not found: {panel_id}")

    def _resolve_collection_panel_id_locked(
        self,
        workspace: WorkspaceState,
        panel_id: str | None,
    ) -> str:
        """Resolve the panel a collection command writes to.

        Collection commands are panel-scoped but the panel is optional: the
        canonical Samples panel is the default, so every workspace-scoped
        caller (CLI, Python API, the built-in panels) keeps working unchanged.
        """

        if panel_id is None:
            return SAMPLES_PANEL_STATE_ID
        return self._resolve_panel_state_id_locked(workspace, panel_id)

    def resolve_collection_panel_id(
        self,
        workspace_id: str,
        panel_id: str | None = None,
    ) -> str:
        """Public form of the collection-command panel resolution.

        Raises ``KeyError`` when the workspace has no such panel, which the
        command service reports as ``not_found``.
        """

        with self._lock:
            workspace = self.get_workspace(workspace_id)
            return self._resolve_collection_panel_id_locked(workspace, panel_id)

    def _get_panel_state_entry_locked(
        self,
        workspace: WorkspaceState,
        panel_id: str,
        *,
        create: bool = False,
    ) -> tuple[str, PanelStateEntry]:
        resolved_panel_id = self._resolve_panel_state_id_locked(workspace, panel_id)
        entry = workspace.ui.panels.get(resolved_panel_id)
        if entry is None:
            if not create:
                return resolved_panel_id, PanelStateEntry()
            entry = PanelStateEntry()
            workspace.ui.panels[resolved_panel_id] = entry
        return resolved_panel_id, entry

    def _prune_panel_states_locked(self, workspace: WorkspaceState) -> None:
        retained_panel_ids = {panel.id for panel in workspace.ui.custom_panels}
        retained_panel_ids.update(RESERVED_PANEL_STATE_IDS)
        workspace.ui.panels = {
            panel_id: state
            for panel_id, state in workspace.ui.panels.items()
            if panel_id in retained_panel_ids
        }

    def _seed_default_panel_state_locked(
        self,
        workspace: WorkspaceState,
        panel: PanelInstance,
        initial_state: dict[str, Any] | None = None,
    ) -> None:
        """Seed a panel's runtime state when it enters the workspace.

        Without ``initial_state`` this only fills in the panel definition's
        defaults, and only for a panel the workspace has never seen. With
        ``initial_state`` the caller is authoring the panel's opening state, so
        it wins over whatever a previous run of the same workspace left behind:
        the result is the definition defaults with the authored state merged on
        top.
        """

        definition = self._definition_for_panel_spec_locked(panel)
        if initial_state is None and (definition is None or panel.id in workspace.ui.panels):
            return

        state = _json_object_copy(definition.default_state) if definition is not None else {}
        if (
            definition is not None
            and definition.panel_type == "samples"
            and workspace.dataset_name
        ):
            state.update(
                _samples_collection_state(
                    self._opening_samples_collection_locked(workspace, panel)
                )
            )

        if initial_state is None:
            if state:
                workspace.ui.panels[panel.id] = PanelStateEntry(state=state)
            return

        state = _json_merge_patch(state, _json_object_copy(dict(initial_state)))
        validate_json_contract(
            state,
            definition.state_schema if definition is not None else None,
            label=f"panel {panel.id!r} state",
        )
        existing = workspace.ui.panels.get(panel.id)
        workspace.ui.panels[panel.id] = PanelStateEntry(
            state=state,
            state_revision=existing.state_revision + 1 if existing is not None else 0,
        )

    def _opening_samples_collection_locked(
        self,
        workspace: WorkspaceState,
        panel: PanelInstance,
    ) -> CollectionState:
        """The collection a Samples panel shows when it first enters the workspace.

        A view that authors ``collection_id`` on a Samples panel has said what
        the panel opens on, so its runtime state starts there whenever the
        workspace stores that collection; the panel's own id does not matter.
        Anything else -- no authored collection, or one the workspace does not
        know -- opens on every sample, as before.
        """

        authored = _authored_collection_id(panel)
        if authored is not None:
            stored = workspace.collections.get(authored)
            if stored is not None:
                return stored
        return self._build_all_collection_locked(workspace)

    def _reopen_samples_collection_locked(
        self,
        workspace: WorkspaceState,
        panel: PanelInstance,
    ) -> None:
        """Move a Samples panel the workspace already knows onto its newly authored collection.

        A previous run's state normally survives re-applying a view, so a
        visitor's navigation is not undone by a restart. Changing the authored
        ``collection_id`` is the author speaking again, and it wins the same
        way authored initial state does.
        """

        definition = self._definition_for_panel_spec_locked(panel)
        if definition is None or definition.panel_type != "samples" or not workspace.dataset_name:
            return
        existing = workspace.ui.panels.get(panel.id)
        if existing is None:
            return
        state = dict(existing.state)
        state.update(
            _samples_collection_state(self._opening_samples_collection_locked(workspace, panel))
        )
        if state == existing.state:
            return
        workspace.ui.panels[panel.id] = PanelStateEntry(
            state=state,
            state_revision=existing.state_revision + 1,
        )

    def _apply_initial_panel_states_locked(
        self,
        workspace: WorkspaceState,
        panels: list[PanelInstance],
        initial_panel_states: dict[str, Any] | None,
    ) -> bool:
        """Apply authored opening state to panels, reporting whether it changed anything."""

        if not initial_panel_states:
            return False
        changed = False
        for panel in panels:
            initial_state = initial_panel_states.get(panel.id)
            if initial_state is None:
                continue
            before = workspace.ui.panels.get(panel.id)
            self._seed_default_panel_state_locked(workspace, panel, initial_state)
            after = workspace.ui.panels.get(panel.id)
            if before is not None and after is not None and before.state == after.state:
                # Re-applying identical state should not look like an edit.
                workspace.ui.panels[panel.id] = before
                continue
            changed = True
        return changed

    def get_panel_state(
        self,
        workspace_id: str,
        panel_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            resolved_panel_id, entry = self._get_panel_state_entry_locked(
                workspace,
                panel_id,
                create=False,
            )
            return {
                "panel_id": resolved_panel_id,
                **entry.to_dict(),
            }

    def patch_panel_state(
        self,
        workspace_id: str,
        panel_id: str,
        patch: dict[str, Any],
        *,
        replace_state: bool = False,
        expected_revision: int | None = None,
        source_client_id: str | None = None,
    ) -> WorkspaceState:
        if not isinstance(patch, dict):
            raise ValueError("panel state patch must be a JSON object")

        with self._lock:
            workspace = self.get_workspace(workspace_id)
            resolved_panel_id, entry = self._get_panel_state_entry_locked(
                workspace,
                panel_id,
                create=True,
            )
            if expected_revision is not None and entry.state_revision != expected_revision:
                raise ValueError(
                    "panel state revision conflict: "
                    f"expected {expected_revision}, got {entry.state_revision}"
                )

            next_state = (
                _json_object_copy(patch)
                if replace_state
                else _json_merge_patch(entry.state, patch)
            )
            definition = self._definition_for_panel_id_locked(workspace, resolved_panel_id)
            validate_json_contract(
                next_state,
                definition.state_schema if definition is not None else None,
                label=f"panel {resolved_panel_id!r} state",
            )
            if next_state == entry.state:
                return workspace

            workspace.ui.panels[resolved_panel_id] = PanelStateEntry(
                state=next_state,
                state_revision=entry.state_revision + 1,
            )
            self.workspace_registry.update_workspace(workspace)
            self._bump_version(source_client_id=source_client_id)
            return workspace

    def get_workspace_layout(self, workspace_id: str) -> dict[str, Any]:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            return {
                "layout": (
                    _json_object_copy(workspace.ui.layout)
                    if workspace.ui.layout is not None
                    else None
                ),
                "layout_revision": workspace.ui.layout_revision,
            }

    def set_workspace_layout(
        self,
        workspace_id: str,
        layout: dict[str, Any] | None,
        *,
        expected_revision: int | None = None,
        source_client_id: str | None = None,
    ) -> WorkspaceState:
        if layout is not None and not isinstance(layout, dict):
            raise ValueError("workspace layout must be a JSON object or null")

        with self._lock:
            workspace = self.get_workspace(workspace_id)
            if (
                expected_revision is not None
                and workspace.ui.layout_revision != expected_revision
            ):
                raise ValueError(
                    "workspace layout revision conflict: "
                    f"expected {expected_revision}, got {workspace.ui.layout_revision}"
                )
            next_layout = _json_object_copy(layout) if layout is not None else None
            if next_layout == workspace.ui.layout:
                return workspace
            workspace.ui.layout = next_layout
            workspace.ui.layout_revision += 1
            self.workspace_registry.update_workspace(workspace)
            self._bump_version(source_client_id=source_client_id)
            return workspace

    def _workspace_dataset_id_locked(self, workspace: WorkspaceState) -> str:
        if not workspace.dataset_name:
            raise ValueError(f"Workspace '{workspace.id}' has no active dataset")
        return workspace.dataset_name

    def _store_collection_locked(
        self,
        workspace: WorkspaceState,
        collection: CollectionState,
    ) -> CollectionState:
        workspace.collections[collection.id] = collection
        return collection

    def _build_all_collection_locked(self, workspace: WorkspaceState) -> CollectionState:
        collection = CollectionState(
            id=_stable_collection_id("all", {}),
            dataset_id=self._workspace_dataset_id_locked(workspace),
            entity_set_id="samples",
            kind="all",
            query={},
        )
        return self._store_collection_locked(workspace, collection)

    def _build_label_filter_collection_locked(
        self,
        workspace: WorkspaceState,
        *,
        field: str,
        value: Any,
        source: str | None = None,
    ) -> CollectionState:
        dataset_id = self._workspace_dataset_id_locked(workspace)
        field = field.strip()
        if not field:
            raise ValueError("field must be a non-empty string")
        query = {
            "field": field,
            "op": "eq",
            "value": value,
        }
        if source:
            query["source"] = source
        collection = CollectionState(
            id=_stable_collection_id("filter", query),
            dataset_id=dataset_id,
            entity_set_id="samples",
            kind="filter",
            query=query,
        )
        return self._store_collection_locked(workspace, collection)

    def _build_selection_collection_locked(
        self,
        workspace: WorkspaceState,
        *,
        sample_ids: list[str],
        source: str | None = None,
    ) -> CollectionState:
        query: dict[str, Any] = {"ids": list(sample_ids)}
        if source:
            query["source"] = source
        collection = CollectionState(
            id=_stable_collection_id("selection", query),
            dataset_id=self._workspace_dataset_id_locked(workspace),
            entity_set_id="samples",
            kind="selection",
            query=query,
        )
        return self._store_collection_locked(workspace, collection)

    def _build_neighbors_collection_locked(
        self,
        workspace: WorkspaceState,
        query: SimilarityQueryState,
    ) -> CollectionState:
        dataset_id = self._workspace_dataset_id_locked(workspace)
        if query.query_text:
            collection_query: dict[str, Any] = {
                "queryText": query.query_text,
                "indexId": index_id_for_space_key(query.space_key) if query.space_key else None,
                "layoutId": query.layout_key,
                "spaceKey": query.space_key,
                "k": query.k,
            }
            if query.source:
                collection_query["source"] = query.source
            collection = CollectionState(
                id=_stable_collection_id("search", collection_query),
                dataset_id=dataset_id,
                entity_set_id="samples",
                kind="search",
                query=collection_query,
            )
            return self._store_collection_locked(workspace, collection)

        if not query.anchor_sample_id:
            raise ValueError("Similarity retrieval requires anchor_sample_id or query_text")

        anchor = EntityRef(
            dataset_id=dataset_id,
            entity_set_id="samples",
            entity_id=query.anchor_sample_id,
        )
        collection_query = {
            "anchor": anchor.to_dict(),
            "indexId": index_id_for_space_key(query.space_key) if query.space_key else None,
            "layoutId": query.layout_key,
            "spaceKey": query.space_key,
            "k": query.k,
        }
        if query.source:
            collection_query["source"] = query.source
        collection = CollectionState(
            id=_stable_collection_id("neighbors", collection_query),
            dataset_id=dataset_id,
            entity_set_id="samples",
            kind="neighbors",
            query=collection_query,
        )
        return self._store_collection_locked(workspace, collection)

    def _set_samples_filter_locked(
        self,
        workspace: WorkspaceState,
        collection: CollectionState | None,
        *,
        panel_id: str = SAMPLES_PANEL_STATE_ID,
    ) -> bool:
        resolved_panel_id, entry = self._get_panel_state_entry_locked(
            workspace,
            panel_id,
            create=collection is not None,
        )
        if collection is None:
            if (
                entry.state.get("mode") != "collection"
                or _samples_panel_collection_kind(entry.state) != "filter"
            ):
                return False
            next_state = _json_object_copy(entry.state)
            next_state.pop("mode", None)
            next_state.pop("retrieval", None)
            next_state.update(
                _samples_collection_state(self._build_all_collection_locked(workspace))
            )
        else:
            next_state = _json_merge_patch(entry.state, _samples_filter_state(collection))
            next_state["collection"] = collection.to_dict()
            next_state["collection_id"] = collection.id

        if next_state == entry.state:
            return False

        workspace.ui.panels[resolved_panel_id] = PanelStateEntry(
            state=next_state,
            state_revision=entry.state_revision + 1,
        )
        return True

    def _set_samples_retrieval_locked(
        self,
        workspace: WorkspaceState,
        query: SimilarityQueryState | None,
        *,
        panel_id: str = SAMPLES_PANEL_STATE_ID,
    ) -> bool:
        resolved_panel_id, entry = self._get_panel_state_entry_locked(
            workspace,
            panel_id,
            create=query is not None,
        )
        if query is None:
            should_clear_collection = (
                entry.state.get("mode") == "retrieval"
                or _samples_panel_collection_kind(entry.state) in {"neighbors", "search"}
            )
            next_state = _json_object_copy(entry.state)
            next_state.pop("retrieval", None)
            if next_state.get("mode") == "retrieval":
                next_state.pop("mode", None)
            if should_clear_collection:
                next_state.update(
                    _samples_collection_state(self._build_all_collection_locked(workspace))
                )
        else:
            collection = self._build_neighbors_collection_locked(workspace, query)
            next_state = _json_object_copy(entry.state)
            next_state.update(_samples_retrieval_state(query, collection))
            next_state["collection"] = collection.to_dict()
            next_state["collection_id"] = collection.id

        if next_state == entry.state:
            return False

        workspace.ui.panels[resolved_panel_id] = PanelStateEntry(
            state=next_state,
            state_revision=entry.state_revision + 1,
        )
        return True

    def set_samples_filter(
        self,
        workspace_id: str,
        *,
        field: str = "label",
        value: Any,
        source: str | None = None,
        panel_id: str | None = None,
    ) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            target_panel_id = self._resolve_collection_panel_id_locked(workspace, panel_id)
            collection = self._build_label_filter_collection_locked(
                workspace,
                field=field,
                value=value,
                source=source,
            )
            workspace.ui.selected_ids = []
            self._set_samples_filter_locked(workspace, collection, panel_id=target_panel_id)
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def clear_samples_filter(
        self,
        workspace_id: str,
        *,
        panel_id: str | None = None,
    ) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            target_panel_id = self._resolve_collection_panel_id_locked(workspace, panel_id)
            self._set_samples_filter_locked(workspace, None, panel_id=target_panel_id)
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def create_collection(
        self,
        workspace_id: str,
        sample_ids: list[str],
        *,
        name: str | None = None,
    ) -> CollectionState:
        """Persist an explicit, ordered list of samples as a workspace collection.

        The returned collection is durable workspace state: panels can bind to
        its id through props, and a static export materializes it because the
        view references it.
        """

        unique_ids = list(
            dict.fromkeys(str(item).strip() for item in sample_ids if str(item).strip())
        )
        if not unique_ids:
            raise ValueError("create_collection requires at least one sample id")

        dataset = self.get_dataset(workspace_id=workspace_id)
        existing_ids = {sample.id for sample in dataset.get_samples_by_ids(unique_ids)}
        missing_ids = [sample_id for sample_id in unique_ids if sample_id not in existing_ids]
        if missing_ids:
            preview = ", ".join(missing_ids[:5])
            suffix = "" if len(missing_ids) <= 5 else f", and {len(missing_ids) - 5} more"
            raise KeyError(f"Samples not found: {preview}{suffix}")

        with self._lock:
            workspace = self.get_workspace(workspace_id)
            collection = self._build_selection_collection_locked(
                workspace,
                sample_ids=unique_ids,
                source=name,
            )
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return collection

    def list_collections(self, workspace_id: str) -> list[CollectionState]:
        """Return the workspace's stored collections, ordered by id."""

        with self._lock:
            workspace = self.get_workspace(workspace_id)
            return [workspace.collections[key] for key in sorted(workspace.collections)]

    def set_active_layout(self, workspace_id: str, layout_key: str | None) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            workspace.ui.active_layout_key = layout_key
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def set_selection(self, workspace_id: str, sample_ids: list[str]) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            workspace.ui.selected_ids = list(dict.fromkeys(sample_ids))
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def set_samples_selection(
        self,
        workspace_id: str,
        sample_ids: list[str],
        *,
        focus: bool = True,
        source: str | None = None,
        panel_id: str | None = None,
    ) -> WorkspaceState:
        """Atomically show explicit rows in Samples and synchronize map selection."""

        unique_ids = list(dict.fromkeys(str(item).strip() for item in sample_ids if str(item).strip()))
        dataset = self.get_dataset(workspace_id=workspace_id)
        existing_ids = {sample.id for sample in dataset.get_samples_by_ids(unique_ids)}
        missing_ids = [sample_id for sample_id in unique_ids if sample_id not in existing_ids]
        if missing_ids:
            preview = ", ".join(missing_ids[:5])
            suffix = "" if len(missing_ids) <= 5 else f", and {len(missing_ids) - 5} more"
            raise KeyError(f"Samples not found: {preview}{suffix}")

        with self._lock:
            workspace = self.get_workspace(workspace_id)
            resolved_panel_id, entry = self._get_panel_state_entry_locked(
                workspace,
                self._resolve_collection_panel_id_locked(workspace, panel_id),
                create=True,
            )
            next_revision = entry.state_revision + 1
            next_state = _json_object_copy(entry.state)
            next_state.pop("retrieval", None)
            if unique_ids:
                collection = self._build_selection_collection_locked(
                    workspace,
                    sample_ids=unique_ids,
                    source=source,
                )
                next_state.update(
                    _samples_selection_state(
                        collection,
                        focus=focus,
                        state_revision=next_revision,
                    )
                )
            else:
                collection = self._build_all_collection_locked(workspace)
                next_state.update(
                    {
                        "mode": "collection",
                        "retrieval": None,
                        **_samples_collection_state(collection),
                        "focus_request": (
                            {"kind": "all", "revision": next_revision} if focus else None
                        ),
                    }
                )

            workspace.ui.selected_ids = unique_ids
            workspace.ui.panels[resolved_panel_id] = PanelStateEntry(
                state=next_state,
                state_revision=next_revision,
            )
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def get_samples_retrieval_query(
        self,
        workspace_id: str,
        *,
        panel_id: str | None = None,
    ) -> SimilarityQueryState | None:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            return _samples_panel_retrieval_query(
                workspace.ui.panels,
                self._resolve_collection_panel_id_locked(workspace, panel_id),
            )

    def set_samples_retrieval(
        self,
        workspace_id: str,
        query: SimilarityQueryState | None,
        *,
        panel_id: str | None = None,
    ) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            target_panel_id = self._resolve_collection_panel_id_locked(workspace, panel_id)
            changed = False
            if query is not None:
                if workspace.ui.selected_ids:
                    workspace.ui.selected_ids = []
                    changed = True
            changed = (
                self._set_samples_retrieval_locked(workspace, query, panel_id=target_panel_id)
                or changed
            )
            if changed:
                self.workspace_registry.update_workspace(workspace)
                self._bump_version()
            return workspace

    def clear_samples_retrieval(
        self,
        workspace_id: str,
        *,
        panel_id: str | None = None,
    ) -> WorkspaceState:
        return self.set_samples_retrieval(workspace_id, None, panel_id=panel_id)

    def patch_ui_state(
        self,
        workspace_id: str,
        *,
        set_active_layout: bool = False,
        active_layout_key: str | None = None,
        set_selection: bool = False,
        selected_ids: list[str] | None = None,
        source_client_id: str | None = None,
    ) -> WorkspaceState:
        """Apply multiple UI-state updates under one runtime version bump."""
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            changed = False
            next_selected_ids = (
                list(dict.fromkeys(selected_ids or []))
                if set_selection
                else list(workspace.ui.selected_ids)
            )

            if set_active_layout and workspace.ui.active_layout_key != active_layout_key:
                workspace.ui.active_layout_key = active_layout_key
                changed = True

            if set_selection:
                if workspace.ui.selected_ids != next_selected_ids:
                    workspace.ui.selected_ids = next_selected_ids
                    changed = True
                active_retrieval = _samples_panel_retrieval_query(workspace.ui.panels)
                if (
                    active_retrieval is not None
                    and active_retrieval.anchor_sample_id
                    not in workspace.ui.selected_ids
                ):
                    self._set_samples_retrieval_locked(workspace, None)
                    changed = True

            if changed:
                self.workspace_registry.update_workspace(workspace)
                self._bump_version(source_client_id=source_client_id)
            return workspace

    def resolve_similarity_query(
        self,
        workspace_id: str,
        sample_id: str,
        *,
        layout_key: str | None = None,
        index_id: str | None = None,
        space_key: str | None = None,
        k: int = 18,
        source: str | None = None,
    ) -> SimilarityQueryState:
        dataset = self.get_dataset(workspace_id=workspace_id)
        try:
            dataset[sample_id]
        except KeyError as exc:
            raise KeyError(f"Sample not found: {sample_id}") from exc

        resolved_layout_key, resolved_space_key = self._resolve_retrieval_context(
            workspace_id=workspace_id,
            layout_key=layout_key,
            index_id=index_id,
            space_key=space_key,
        )

        try:
            limit = int(k)
        except (TypeError, ValueError):
            limit = 18

        return SimilarityQueryState(
            anchor_sample_id=sample_id,
            layout_key=resolved_layout_key,
            space_key=resolved_space_key,
            k=max(1, min(limit, 100)),
            source=source,
        )

    def resolve_text_retrieval_query(
        self,
        workspace_id: str,
        query_text: str,
        *,
        layout_key: str | None = None,
        index_id: str | None = None,
        space_key: str | None = None,
        k: int = 18,
        source: str | None = None,
    ) -> SimilarityQueryState:
        text = str(query_text or "").strip()
        if not text:
            raise ValueError("query_text must be a non-empty string")

        requested_context = any((layout_key, index_id, space_key))
        resolved_layout_key, resolved_space_key = self._resolve_retrieval_context(
            workspace_id=workspace_id,
            layout_key=layout_key,
            index_id=index_id,
            space_key=space_key,
        )

        dataset = self.get_dataset(workspace_id=workspace_id)
        spaces = dataset.list_spaces()
        from hyperview.embeddings.engine import get_engine

        engine = get_engine(provider_registry=self.provider_registry)

        def supports_text(candidate_space_key: str | None) -> bool:
            if candidate_space_key is None:
                return False
            try:
                spec = dataset._embedding_spec_for_space(candidate_space_key)
                return "text" in engine.supported_modalities(spec)
            except (ImportError, KeyError, RuntimeError, ValueError):
                return False

        if not supports_text(resolved_space_key):
            if requested_context:
                raise ValueError(
                    f"Embedding space {resolved_space_key!r} does not support text queries"
                )
            compatible_space = next(
                (space for space in spaces if supports_text(space.space_key)),
                None,
            )
            if compatible_space is None:
                raise ValueError("No text-capable embedding space is available")
            resolved_space_key = compatible_space.space_key
            matching_layout = next(
                (
                    item
                    for item in dataset.list_layouts()
                    if item.space_key == resolved_space_key
                ),
                None,
            )
            resolved_layout_key = (
                matching_layout.layout_key if matching_layout is not None else None
            )

        try:
            limit = int(k)
        except (TypeError, ValueError):
            limit = 18

        return SimilarityQueryState(
            query_text=text,
            layout_key=resolved_layout_key,
            space_key=resolved_space_key,
            k=max(1, min(limit, 100)),
            source=source,
        )

    def _resolve_retrieval_context(
        self,
        *,
        workspace_id: str,
        layout_key: str | None,
        index_id: str | None,
        space_key: str | None,
    ) -> tuple[str | None, str | None]:
        indexed_space_key = space_key_from_index_ref(index_id)
        if index_id is not None and indexed_space_key is None:
            raise ValueError("index_id must identify an index")
        if space_key is not None and indexed_space_key is not None and space_key != indexed_space_key:
            raise ValueError("space_key does not match the requested index_id")
        resolved_space_key = indexed_space_key or space_key
        resolved_layout_key = layout_key
        if layout_key is not None:
            dataset = self.get_dataset(workspace_id=workspace_id)
            layout = next(
                (item for item in dataset.list_layouts() if item.layout_key == layout_key),
                None,
            )
            if layout is None:
                raise LookupError(f"Layout not found: {layout_key}")
            if resolved_space_key is not None and resolved_space_key != layout.space_key:
                raise ValueError("space_key does not match the requested layout_key")
            resolved_space_key = layout.space_key

        if resolved_space_key is not None:
            dataset = self.get_dataset(workspace_id=workspace_id)
            space = next(
                (item for item in dataset.list_spaces() if item.space_key == resolved_space_key),
                None,
            )
            if space is None:
                raise LookupError(f"Space not found: {resolved_space_key}")
        else:
            workspace = self.get_workspace(workspace_id)
            dataset = self.get_dataset(workspace_id=workspace_id)
            if workspace.ui.active_layout_key:
                active_layout = next(
                    (
                        item
                        for item in dataset.list_layouts()
                        if item.layout_key == workspace.ui.active_layout_key
                    ),
                    None,
                )
                if active_layout is not None:
                    resolved_layout_key = active_layout.layout_key
                    resolved_space_key = active_layout.space_key
            if resolved_space_key is None:
                spaces = dataset.list_spaces()
                if spaces:
                    resolved_space_key = spaces[0].space_key

        return resolved_layout_key, resolved_space_key

    def set_layout_view(
        self,
        workspace_id: str,
        layout_key: str,
        view: LayoutViewState,
    ) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            current = workspace.ui.layout_views.get(layout_key)
            if current is not None and current.to_dict() == view.to_dict():
                return workspace
            workspace.ui.layout_views[layout_key] = view
            self.workspace_registry.update_workspace(workspace)
            # Camera saves are high-frequency local UI state; avoid forcing
            # runtime snapshots that can overwrite in-progress selection state.
            return workspace

    def build_custom_panel(
        self,
        workspace_id: str,
        *,
        panel_id: str,
        title: str | None = None,
        builtin_panel: str | None = None,
        extension: str | None = None,
        extension_panel: str | None = None,
        layout_key: str | None = None,
        position: str | None = None,
        reference_panel_id: str | None = None,
        direction: str | None = None,
        width: int | None = None,
        height: int | None = None,
        min_width: int | None = None,
        min_height: int | None = None,
        max_width: int | None = None,
        max_height: int | None = None,
        visible: bool = True,
        props: dict[str, Any] | None = None,
        geometry: str | None = None,
        layout_dimension: int | None = None,
        require_resolved_layout: bool = True,
    ) -> PanelInstance:
        """Resolve a transport-level panel request into a placed panel.

        What the request asks for is read off the fields that name a panel, in
        the order the CLI's old ``--kind auto`` resolved them: an extension
        reference names an extension panel, a built-in panel type names a
        shipped one, and a bare layout key names a scatter bound to that
        layout. There is no ``kind`` to disagree with them.
        """

        if extension or extension_panel:
            requested = "extension"
        elif builtin_panel:
            requested = "builtin"
        elif layout_key:
            requested = "scatter"
        else:
            raise ValueError(
                f"Panel '{panel_id}' does not say what to open: pass builtin_panel for a "
                "shipped panel, extension and extension_panel for an extension panel, or "
                "layout_key for a scatter panel."
            )

        if requested == "builtin":
            builtin_panel_type = str(builtin_panel or "").strip()
            definition = self.get_panel_definition(builtin_panel_type, source="shipped")
            if definition is None:
                raise ValueError(f"Unknown built-in panel type: {builtin_panel_type}")
            layout = _panel_layout_fields(
                definition.default_layout,
                position=position,
                reference_panel_id=reference_panel_id,
                direction=direction,
                width=width,
                height=height,
                min_width=min_width,
                min_height=min_height,
                max_width=max_width,
                max_height=max_height,
            )
            merged_props = merge_default_props(definition, props)
            validate_json_contract(merged_props, definition.props_schema, label="panel props")
            return PanelInstance(
                id=panel_id,
                title=title or definition.title or definition.label,
                panel_type=definition.panel_type,
                source=definition.source,
                renderer=definition.renderer,
                builtin_panel=definition.panel_type,
                **layout,
                visible=visible,
                props=merged_props,
            )

        if requested == "extension":
            if not extension:
                raise ValueError("extension is required for extension panels")
            if not extension_panel:
                raise ValueError("extension_panel is required for extension panels")
            installation = self.get_extension(extension)
            if installation is None:
                raise LookupError(f"Extension not found: {extension}")
            manifest_panel = next(
                (panel for panel in installation.manifest.panels if panel.id == extension_panel),
                None,
            )
            if manifest_panel is None:
                raise LookupError(f"Extension panel not found: {extension}/{extension_panel}")
            module_name = manifest_panel.module_file()
            if module_name is None:
                raise ValueError(
                    f"Extension panel '{extension}/{extension_panel}' does not declare a module renderer"
                )
            module_file = resolve_panel_source(installation.manifest.folder, module_name)
            definition = manifest_panel.to_definition(
                installation.manifest.name,
                source=installation.source,
            )
            layout = _panel_layout_fields(
                definition.default_layout,
                position=position,
                reference_panel_id=reference_panel_id,
                direction=direction,
                width=width,
                height=height,
                min_width=min_width,
                min_height=min_height,
                max_width=max_width,
                max_height=max_height,
            )
            merged_props = merge_default_props(definition, props)
            validate_json_contract(merged_props, definition.props_schema, label="panel props")
            return PanelInstance(
                id=panel_id,
                title=title or definition.title or definition.label,
                panel_type=definition.panel_type,
                source=definition.source,
                renderer=definition.renderer,
                extension=extension,
                extension_panel=extension_panel,
                module_file=str(module_file),
                **layout,
                visible=visible,
                props=merged_props,
            )

        if requested == "scatter":
            if not layout_key:
                raise ValueError("layout_key is required for scatter panels")
            if geometry is None or layout_dimension is None:
                try:
                    dataset = self.get_dataset(workspace_id)
                except ValueError:
                    if require_resolved_layout:
                        raise
                    dataset = None
                layout_info = None
                if dataset is not None:
                    layout_info = next(
                        (
                            layout
                            for layout in dataset.list_layouts()
                            if layout.layout_key == layout_key
                        ),
                        None,
                    )
                if layout_info is None:
                    if require_resolved_layout:
                        raise LookupError(f"Layout not found: {layout_key}")
                else:
                    geometry = geometry or layout_info.geometry
                    layout_dimension = (
                        layout_dimension
                        if layout_dimension is not None
                        else parse_layout_dimension(layout_info.layout_key)
                    )
            if not title:
                raise ValueError("title is required for scatter panels")
            layout = _panel_layout_fields(
                None,
                position=position,
                reference_panel_id=reference_panel_id,
                direction=direction,
                width=width,
                height=height,
                min_width=min_width,
                min_height=min_height,
                max_width=max_width,
                max_height=max_height,
            )
            definition = self.get_panel_definition("scatter", source="shipped")
            if definition is None:
                raise RuntimeError("Packaged scatter panel definition is unavailable")
            return PanelInstance(
                id=panel_id,
                title=title,
                panel_type="scatter",
                source=definition.source,
                renderer=definition.renderer,
                builtin_panel="scatter",
                layout_key=layout_key,
                geometry=geometry,
                layout_dimension=layout_dimension,
                **layout,
                visible=visible,
                props=merge_default_props(
                    definition,
                    props,
                ),
            )

        raise AssertionError("unreachable: every requested panel shape is handled above")

    def add_runtime_panel(
        self,
        workspace_id: str,
        *,
        panel_id: str,
        title: str | None = None,
        builtin_panel: str | None = None,
        extension: str | None = None,
        extension_panel: str | None = None,
        layout_key: str | None = None,
        position: str | None = None,
        reference_panel_id: str | None = None,
        direction: str | None = None,
        width: int | None = None,
        height: int | None = None,
        min_width: int | None = None,
        min_height: int | None = None,
        max_width: int | None = None,
        max_height: int | None = None,
        visible: bool = True,
        props: dict[str, Any] | None = None,
        geometry: str | None = None,
        layout_dimension: int | None = None,
        require_resolved_layout: bool = True,
    ) -> WorkspaceState:
        panel = self.build_custom_panel(
            workspace_id,
            panel_id=panel_id,
            title=title,
            builtin_panel=builtin_panel,
            extension=extension,
            extension_panel=extension_panel,
            layout_key=layout_key,
            position=position,
            reference_panel_id=reference_panel_id,
            direction=direction,
            width=width,
            height=height,
            min_width=min_width,
            min_height=min_height,
            max_width=max_width,
            max_height=max_height,
            visible=visible,
            props=props,
            geometry=geometry,
            layout_dimension=layout_dimension,
            require_resolved_layout=require_resolved_layout,
        )
        return self.add_custom_panel(workspace_id, panel)

    def add_custom_panel(
        self,
        workspace_id: str,
        panel: PanelInstance,
        *,
        initial_state: dict[str, Any] | None = None,
    ) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            panels = [
                existing for existing in workspace.ui.custom_panels if existing.id != panel.id
            ]
            panels.append(panel)
            workspace.ui.custom_panels = panels
            self._seed_default_panel_state_locked(workspace, panel, initial_state)
            workspace.ui.view_revision += 1
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def update_custom_panel(
        self,
        workspace_id: str,
        panel_id: str,
        *,
        title: str | None = None,
        position: Literal["center", "right", "bottom"] | None = None,
        reference_panel_id: str | None | object = _UNSET,
        direction: Literal["right", "left", "above", "below", "within"] | None | object = _UNSET,
        width: int | None | object = _UNSET,
        height: int | None | object = _UNSET,
        min_width: int | None | object = _UNSET,
        min_height: int | None | object = _UNSET,
        max_width: int | None | object = _UNSET,
        max_height: int | None | object = _UNSET,
        visible: bool | None = None,
        active: bool | None = None,
        props: dict[str, Any] | None = None,
    ) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            next_panels: list[PanelInstance] = []
            found = False
            changed = False

            for panel in workspace.ui.custom_panels:
                if panel.id != panel_id:
                    next_panels.append(panel)
                    continue

                found = True
                next_panel = panel
                if title is not None and title != panel.title:
                    next_panel = replace(next_panel, title=title)
                    changed = True
                if position is not None:
                    if position not in {"center", "right", "bottom"}:
                        raise ValueError("position must be one of center, right, bottom")
                    if position != panel.position:
                        next_panel = replace(next_panel, position=position)
                        changed = True
                if reference_panel_id is not _UNSET:
                    next_reference_panel_id = (
                        None if reference_panel_id is None else str(reference_panel_id)
                    )
                    if next_reference_panel_id != panel.reference_panel_id:
                        next_panel = replace(
                            next_panel,
                            reference_panel_id=next_reference_panel_id,
                        )
                        changed = True
                if direction is not _UNSET:
                    if direction is not None and direction not in {
                        "right",
                        "left",
                        "above",
                        "below",
                        "within",
                    }:
                        raise ValueError("direction must be one of right, left, above, below, within")
                    next_direction = direction if direction is None else str(direction)
                    if next_direction != panel.direction:
                        next_panel = replace(next_panel, direction=next_direction)
                        changed = True
                for field_name, value in {
                    "width": width,
                    "height": height,
                    "min_width": min_width,
                    "min_height": min_height,
                    "max_width": max_width,
                    "max_height": max_height,
                }.items():
                    if value is _UNSET:
                        continue
                    parsed_value = None if value is None else _positive_int_or_none(value)  # type: ignore[arg-type]
                    if getattr(panel, field_name) != parsed_value:
                        next_panel = replace(next_panel, **{field_name: parsed_value})
                        changed = True
                if visible is not None and visible != panel.visible:
                    next_panel = replace(next_panel, visible=visible)
                    changed = True
                if props is not None and props != panel.props:
                    definition = self._definition_for_panel_spec_locked(panel)
                    validate_json_contract(
                        props,
                        definition.props_schema if definition is not None else None,
                        label=f"panel {panel_id!r} props",
                    )
                    next_panel = replace(next_panel, props=dict(props))
                    changed = True
                next_panels.append(next_panel)

            if not found:
                raise KeyError(f"Panel not found: {panel_id}")

            if active is True and workspace.ui.active_panel_id != panel_id:
                workspace.ui.active_panel_id = panel_id
                changed = True
            elif active is False and workspace.ui.active_panel_id == panel_id:
                workspace.ui.active_panel_id = None
                changed = True

            if visible is False and workspace.ui.active_panel_id == panel_id:
                workspace.ui.active_panel_id = None
                changed = True

            if changed:
                workspace.ui.custom_panels = next_panels
                workspace.ui.view_revision += 1
                self.workspace_registry.update_workspace(workspace)
                self._bump_version()
            return workspace

    def replace_custom_panels(
        self,
        workspace_id: str,
        panels: list[PanelInstance],
        *,
        bump_view_revision: bool = True,
        has_explicit_view: bool | None = None,
        active_panel_id: str | None = None,
        initial_panel_states: dict[str, dict[str, Any]] | None = None,
    ) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            next_panels = list(panels)
            _ensure_unique_panel_ids(next_panels)
            next_has_explicit_view = (
                workspace.ui.has_explicit_view if has_explicit_view is None else has_explicit_view
            )
            next_active_panel_id = active_panel_id
            if next_active_panel_id is not None and not any(
                panel.id == next_active_panel_id for panel in next_panels
            ):
                raise ValueError(f"Active panel is not in the view: {next_active_panel_id}")

            panels_changed = [
                panel.to_storage_dict() for panel in workspace.ui.custom_panels
            ] != [panel.to_storage_dict() for panel in next_panels]
            view_mode_changed = workspace.ui.has_explicit_view != next_has_explicit_view
            persisted_layout_changed = workspace.ui.layout is not None
            if (
                not panels_changed
                and not view_mode_changed
                and not persisted_layout_changed
                and workspace.ui.active_panel_id == next_active_panel_id
            ):
                if self._apply_initial_panel_states_locked(
                    workspace,
                    next_panels,
                    initial_panel_states,
                ):
                    self.workspace_registry.update_workspace(workspace)
                    self._bump_version()
                return workspace

            previous_panels = {panel.id: panel for panel in workspace.ui.custom_panels}
            workspace.ui.custom_panels = next_panels
            workspace.ui.has_explicit_view = next_has_explicit_view
            workspace.ui.active_panel_id = next_active_panel_id
            if panels_changed or view_mode_changed or persisted_layout_changed:
                workspace.ui.layout = None
                workspace.ui.layout_revision += 1
            self._prune_panel_states_locked(workspace)
            for panel in next_panels:
                self._seed_default_panel_state_locked(workspace, panel)
                previous = previous_panels.get(panel.id)
                if previous is not None and _authored_collection_id(
                    previous
                ) != _authored_collection_id(panel):
                    self._reopen_samples_collection_locked(workspace, panel)
            self._apply_initial_panel_states_locked(
                workspace,
                next_panels,
                initial_panel_states,
            )
            if bump_view_revision:
                workspace.ui.view_revision += 1
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def remove_custom_panel(self, workspace_id: str, panel_id: str) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            workspace.ui.custom_panels = [
                panel for panel in workspace.ui.custom_panels if panel.id != panel_id
            ]
            workspace.ui.panels.pop(panel_id, None)
            if workspace.ui.active_panel_id == panel_id:
                workspace.ui.active_panel_id = None
            workspace.ui.view_revision += 1
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def get_custom_panel(self, workspace_id: str, panel_id: str) -> PanelInstance:
        workspace = self.get_workspace(workspace_id)
        for panel in workspace.ui.custom_panels:
            if panel.id == panel_id:
                return panel
        raise ValueError(f"Unknown panel '{panel_id}' for workspace '{workspace.id}'")

    def register_job(
        self,
        *,
        kind: str,
        workspace_id: str,
        dataset_name: str | None,
        params: dict[str, Any],
    ) -> JobState:
        job = JobState(
            id=uuid.uuid4().hex,
            kind=kind,
            workspace_id=workspace_id,
            dataset_name=dataset_name,
            params=params,
        )
        with self._lock:
            self.job_registry.update(job)
            self._job_cancel_events[job.id] = threading.Event()
            self._bump_version()
        return job

    def list_jobs(self) -> list[JobState]:
        with self._lock:
            return self.job_registry.list()

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            return self.job_registry.get(job_id)

    def cancel_job(self, job_id: str) -> JobState:
        """Request cooperative cancellation of a queued or running job."""

        with self._lock:
            job = self.job_registry.get(job_id)
            if job is None:
                raise ValueError(f"Unknown job: {job_id}")
            if job.status in {"completed", "failed", "cancelled", "interrupted"}:
                return job
            job.cancellation_requested = True
            self._job_cancel_events.setdefault(job.id, threading.Event()).set()
            if job.status == "queued":
                job.status = "cancelled"
                job.finished_at = _now_ts()
            self.job_registry.update(job)
            self._bump_version()
            return job

    def _check_job_cancelled(self, job_id: str | None = None) -> None:
        if job_id is None:
            job_id = getattr(self._job_worker_context, "job_id", None)
        if job_id is None:
            return
        event = self._job_cancel_events.get(job_id)
        if event is not None and event.is_set():
            raise _JobCancelledError

    def _job_worker_loop(self) -> None:
        while True:
            job_id, target = self._job_queue.get()
            try:
                self._job_worker_context.job_id = job_id
                with self._lock:
                    current = self.job_registry.get(job_id)
                    if current is None or current.status == "cancelled":
                        continue
                    current.status = "running"
                    current.started_at = _now_ts()
                    self.job_registry.update(current)
                    self._bump_version()

                try:
                    self._check_job_cancelled(job_id)
                    result = target()
                    self._check_job_cancelled(job_id)
                except _JobCancelledError:
                    with self._lock:
                        current = self.job_registry.get(job_id)
                        if current is not None:
                            current.status = "cancelled"
                            current.finished_at = _now_ts()
                            self.job_registry.update(current)
                            self._bump_version()
                    continue
                except Exception as exc:  # pragma: no cover - runtime-specific failures
                    with self._lock:
                        current = self.job_registry.get(job_id)
                        if current is not None:
                            current.status = "failed"
                            current.error = f"{type(exc).__name__}: {exc}"
                            current.finished_at = _now_ts()
                            self.job_registry.update(current)
                            self._bump_version()
                    continue

                with self._lock:
                    current = self.job_registry.get(job_id)
                    if current is not None:
                        current.status = "completed"
                        current.result = result
                        current.finished_at = _now_ts()
                        self.job_registry.update(current)
                        self._bump_version()
            finally:
                self._job_worker_context.job_id = None
                self._job_queue.task_done()

    def submit_job(
        self,
        *,
        kind: str,
        workspace_id: str,
        dataset_name: str | None,
        params: dict[str, Any],
        target: Any,
    ) -> JobState:
        job = self.register_job(
            kind=kind, workspace_id=workspace_id, dataset_name=dataset_name, params=params
        )
        self._job_queue.put((job.id, target))
        return job

    def submit_embedding_job(
        self,
        *,
        workspace_id: str,
        dataset_name: str,
        model: str,
        provider: str | None = None,
        checkpoint: str | None = None,
        provider_kwargs: dict[str, Any] | None = None,
        layouts: list[str] | None = None,
        method: str = "umap",
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        activate_layout: bool = True,
    ) -> JobState:
        provider_kwargs = dict(provider_kwargs or {})

        def run() -> dict[str, Any]:
            self._check_job_cancelled()
            dataset = self.get_dataset(workspace_id, dataset_name)
            space_key = dataset.compute_embeddings(
                model=model,
                provider=provider,
                checkpoint=checkpoint,
                show_progress=True,
                _provider_registry=self.provider_registry,
                **provider_kwargs,
            )
            self._check_job_cancelled()

            layout_keys: list[str] = []
            for layout in layouts or []:
                self._check_job_cancelled()
                layout_key = dataset.compute_visualization(
                    space_key=space_key,
                    method=method,
                    layout=layout,
                    n_neighbors=n_neighbors,
                    min_dist=min_dist,
                    metric=metric,
                )
                layout_keys.append(layout_key)
                self._check_job_cancelled()

            self.set_workspace_dataset(workspace_id, dataset_name)
            if activate_layout and layout_keys:
                self.set_active_layout(workspace_id, layout_keys[0])

            return {
                "space_key": space_key,
                "layout_keys": layout_keys,
            }

        return self.submit_job(
            kind="embeddings.compute",
            workspace_id=workspace_id,
            dataset_name=dataset_name,
            params={
                "model": model,
                "provider": provider,
                "checkpoint": checkpoint,
                "layouts": list(layouts or []),
            },
            target=run,
        )

    def submit_layout_job(
        self,
        *,
        workspace_id: str,
        dataset_name: str,
        space_key: str | None,
        layouts: list[str],
        method: str = "umap",
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        activate_layout: bool = True,
    ) -> JobState:
        def run() -> dict[str, Any]:
            self._check_job_cancelled()
            dataset = self.get_dataset(workspace_id, dataset_name)
            layout_keys: list[str] = []
            for layout in layouts:
                self._check_job_cancelled()
                layout_key = dataset.compute_visualization(
                    space_key=space_key,
                    method=method,
                    layout=layout,
                    n_neighbors=n_neighbors,
                    min_dist=min_dist,
                    metric=metric,
                )
                layout_keys.append(layout_key)
                self._check_job_cancelled()
            if activate_layout and layout_keys:
                self.set_active_layout(workspace_id, layout_keys[0])
            return {"layout_keys": layout_keys}

        return self.submit_job(
            kind="layouts.compute",
            workspace_id=workspace_id,
            dataset_name=dataset_name,
            params={"space_key": space_key, "layouts": layouts},
            target=run,
        )

    def get_panel_payload(self, workspace_id: str, panel: PanelInstance) -> dict[str, Any]:
        module_file = panel.resolved_module_file()
        if module_file is None:
            return {"module_src": None}

        revision = self._panel_module_revision(panel) or str(self.version)
        return {
            "module_src": "/api/panels/content/"
            f"{quote(workspace_id, safe='')}/"
            f"{quote(panel.id, safe='')}/"
            f"{quote(module_file.name, safe='')}"
            f"?hv_rev={quote(revision, safe='')}",
        }

    # ------------------------------------------------------------------
    # Extensions and tools
    # ------------------------------------------------------------------

    def list_extensions(self) -> list[ExtensionInstallation]:
        with self._lock:
            return [self._extensions[key] for key in sorted(self._extensions)]

    def get_extension(self, name: str) -> ExtensionInstallation | None:
        with self._lock:
            return self._extensions.get(name)

    def list_panel_definitions(self) -> list[PanelDefinition]:
        with self._lock:
            definitions = list(self._core_panel_definitions)
            for installation in self._extensions.values():
                definitions.extend(
                    panel.to_definition(
                        installation.manifest.name,
                        source=installation.source,
                    )
                    for panel in installation.manifest.panels
                )
            return sorted(
                definitions,
                key=lambda definition: (definition.source, definition.panel_type),
            )

    def get_panel_definition(
        self,
        panel_type: str,
        *,
        source: str | None = None,
        extension: str | None = None,
    ) -> PanelDefinition | None:
        with self._lock:
            return self._get_panel_definition_locked(
                panel_type,
                source=source,
                extension=extension,
            )

    def _get_panel_definition_locked(
        self,
        panel_type: str,
        *,
        source: str | None = None,
        extension: str | None = None,
    ) -> PanelDefinition | None:
        definitions = list(self._core_panel_definitions)
        for installation in self._extensions.values():
            definitions.extend(
                panel.to_definition(
                    installation.manifest.name,
                    source=installation.source,
                )
                for panel in installation.manifest.panels
            )
        for definition in definitions:
            if definition.panel_type != panel_type:
                continue
            if source is not None and definition.source != source:
                continue
            if extension is not None and definition.extension != extension:
                continue
            return definition
        return None

    def list_panel_types(self) -> list[str]:
        """Return every registered panel type, built-in and extension."""

        return sorted({definition.panel_type for definition in self.list_panel_definitions()})

    def find_panel_type(self, panel_type: str) -> PanelTypeMatch | None:
        """Resolve a panel type to its definition and, if any, its extension.

        Panel types are the one name a view needs: ``"samples"`` for a built-in,
        or whatever an installed extension declares (``"<extension>.<panel>"``
        unless the manifest overrides ``panel_type``).
        """

        with self._lock:
            for definition in self._core_panel_definitions:
                if definition.panel_type == panel_type:
                    return PanelTypeMatch(definition=definition)
            for installation in self._extensions.values():
                extension_name = installation.manifest.name
                for entry in installation.manifest.panels:
                    if entry.resolved_panel_type(extension_name) != panel_type:
                        continue
                    return PanelTypeMatch(
                        definition=entry.to_definition(
                            extension_name,
                            source=installation.source,
                        ),
                        extension=extension_name,
                        extension_panel=entry.id,
                    )
        return None

    def find_extension_panel(self, extension: str, panel_id: str) -> PanelTypeMatch | None:
        """Resolve an installed extension's panel by manifest id."""

        with self._lock:
            installation = self._extensions.get(extension)
            if installation is None:
                return None
            entry = next(
                (item for item in installation.manifest.panels if item.id == panel_id),
                None,
            )
            if entry is None:
                return None
            return PanelTypeMatch(
                definition=entry.to_definition(
                    installation.manifest.name,
                    source=installation.source,
                ),
                extension=installation.manifest.name,
                extension_panel=entry.id,
            )

    def _definition_for_panel_spec_locked(
        self,
        panel: PanelInstance,
    ) -> PanelDefinition | None:
        if panel.renders_native():
            return self._get_panel_definition_locked(
                panel.resolved_panel_type(),
                source="shipped",
            )
        if panel.extension and panel.extension_panel:
            installation = self._extensions.get(panel.extension)
            if installation is None:
                return None
            manifest_panel = next(
                (
                    item
                    for item in installation.manifest.panels
                    if item.id == panel.extension_panel
                ),
                None,
            )
            if manifest_panel is None:
                return None
            return manifest_panel.to_definition(
                installation.manifest.name,
                source=installation.source,
            )
        return None

    def _definition_for_panel_id_locked(
        self,
        workspace: WorkspaceState,
        panel_id: str,
    ) -> PanelDefinition | None:
        if panel_id == SAMPLES_PANEL_STATE_ID:
            return self._get_panel_definition_locked("samples", source="shipped")
        panel = next((item for item in workspace.ui.custom_panels if item.id == panel_id), None)
        return self._definition_for_panel_spec_locked(panel) if panel is not None else None

    def install_extension(
        self,
        workspace_id: str,
        folder: Path,
        *,
        add_panels: bool = False,
        source: Literal["extension", "shipped"] = "extension",
    ) -> ExtensionInstallation:
        """Load an extension folder and register its tools + panels."""

        if source not in {"extension", "shipped"}:
            raise ValueError(f"Unsupported extension source: {source}")

        manifest = ExtensionManifest.load(folder)
        loaded = load_extension_tools(manifest)
        prepared_panels: list[PanelInstance] = []
        for panel_entry in manifest.panels:
            # The renderer reference decides how a panel is drawn; where the
            # panel was declared does not. An extension that names a module
            # ships that file, and one that names a native renderer resolves to
            # the frontend component of that name -- or fails at render time if
            # this shell has no such component, which is not an install error.
            module_name = panel_entry.module_file()
            panel_file = (
                resolve_panel_source(manifest.folder, module_name)
                if module_name is not None
                else None
            )
            definition = panel_entry.to_definition(manifest.name, source=source)
            layout = _panel_layout_fields(
                definition.default_layout,
                position=None,
                reference_panel_id=None,
                direction=None,
                width=None,
                height=None,
                min_width=None,
                min_height=None,
                max_width=None,
                max_height=None,
            )
            prepared_panels.append(
                PanelInstance(
                    id=panel_entry.id,
                    title=definition.title or definition.label,
                    panel_type=definition.panel_type,
                    source=definition.source,
                    renderer=definition.renderer,
                    builtin_panel=_native_component_name(definition.renderer),
                    extension=manifest.name,
                    extension_panel=panel_entry.id,
                    module_file=str(panel_file) if panel_file is not None else None,
                    **layout,
                    props=merge_default_props(definition, None),
                )
            )

        with self._lock:
            self.get_workspace(workspace_id)

            previous_installation = self._extensions.get(manifest.name)
            previous_workspace_panels: list[PanelInstance] | None = None
            if previous_installation is not None:
                try:
                    previous_workspace = self.get_workspace(previous_installation.workspace_id)
                except ValueError:
                    previous_workspace = None
                if previous_workspace is not None:
                    previous_workspace_panels = list(previous_workspace.ui.custom_panels)

            installed_panel_ids: list[str] = []
            try:
                if previous_installation is not None:
                    self._uninstall_extension_locked(manifest.name)

                for record in loaded.tools:
                    self.tools.register(record)

                if add_panels:
                    for panel in prepared_panels:
                        self._add_custom_panel_locked(workspace_id, panel)
                        installed_panel_ids.append(panel.id)

                installation = ExtensionInstallation(
                    manifest=manifest,
                    loaded=loaded,
                    workspace_id=workspace_id,
                    source=source,
                    panel_ids=list(installed_panel_ids),
                    add_panels=add_panels,
                )
                self._extensions[manifest.name] = installation
                if add_panels:
                    workspace = self.get_workspace(workspace_id)
                    for panel in prepared_panels:
                        self._seed_default_panel_state_locked(workspace, panel)
                    self.workspace_registry.update_workspace(workspace)
                self._bump_version()
                return installation
            except Exception:
                if installed_panel_ids:
                    workspace = self.get_workspace(workspace_id)
                    workspace.ui.custom_panels = [
                        panel
                        for panel in workspace.ui.custom_panels
                        if panel.id not in installed_panel_ids
                    ]
                    for panel_id in installed_panel_ids:
                        workspace.ui.panels.pop(panel_id, None)
                    workspace.ui.view_revision += 1
                    self.workspace_registry.update_workspace(workspace)

                self.tools.unregister_by_extension(manifest.name)
                unload_extension_modules(loaded)

                if previous_installation is not None:
                    self._extensions[manifest.name] = previous_installation
                    for record in previous_installation.loaded.tools:
                        self.tools.register(record)

                    if previous_workspace_panels is not None:
                        workspace = self.get_workspace(previous_installation.workspace_id)
                        workspace.ui.custom_panels = previous_workspace_panels
                        workspace.ui.view_revision += 1
                        self.workspace_registry.update_workspace(workspace)

                raise

    def install_shipped_extension(
        self,
        workspace_id: str,
        name: str,
        *,
        add_panels: bool = False,
    ) -> ExtensionInstallation:
        """Install an extension package distributed with HyperView."""

        return self.install_extension(
            workspace_id,
            resolve_shipped_extension(name),
            add_panels=add_panels,
            source="shipped",
        )

    def uninstall_extension(self, name: str) -> ExtensionInstallation | None:
        with self._lock:
            return self._uninstall_extension_locked(name)

    def _uninstall_extension_locked(self, name: str) -> ExtensionInstallation | None:
        installation = self._extensions.pop(name, None)
        if installation is None:
            return None

        try:
            workspace = self.get_workspace(installation.workspace_id)
        except ValueError:
            workspace = None

        if workspace is not None:
            workspace.ui.custom_panels = [
                panel
                for panel in workspace.ui.custom_panels
                if panel.id not in installation.panel_ids
            ]
            for panel_id in installation.panel_ids:
                workspace.ui.panels.pop(panel_id, None)
            workspace.ui.view_revision += 1
            self.workspace_registry.update_workspace(workspace)

        self.tools.unregister_by_extension(name)
        unload_extension_modules(installation.loaded)
        self._bump_version()
        return installation

    def reload_extension(self, name: str) -> ExtensionInstallation | None:
        with self._lock:
            installation = self._extensions.get(name)
            if installation is None:
                return None
            folder = installation.manifest.folder
            workspace_id = installation.workspace_id
            add_panels = installation.add_panels
            source = installation.source
        return self.install_extension(
            workspace_id,
            folder,
            add_panels=add_panels,
            source=source,
        )

    def _add_custom_panel_locked(self, workspace_id: str, panel: PanelInstance) -> None:
        workspace = self.get_workspace(workspace_id)
        panels = [existing for existing in workspace.ui.custom_panels if existing.id != panel.id]
        panels.append(panel)
        workspace.ui.custom_panels = panels
        self._seed_default_panel_state_locked(workspace, panel)
        workspace.ui.view_revision += 1
        self.workspace_registry.update_workspace(workspace)

    def extension_storage_dir(self, extension_name: str) -> Path:
        installation = self.get_extension(extension_name)
        if installation is None:
            raise ValueError(f"Unknown extension: {extension_name}")
        storage = installation.manifest.folder / "artifacts"
        storage.mkdir(parents=True, exist_ok=True)
        return storage

    def run_tool(
        self,
        uri: str,
        *,
        workspace_id: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        record = self.tools.get(uri)
        if record is None:
            raise ValueError(f"Unknown tool: {uri}")

        extension_name = record.extension or "default"
        try:
            storage = self.extension_storage_dir(extension_name)
        except ValueError:
            storage = Path.cwd()

        try:
            dataset = self.get_dataset(workspace_id)
        except ValueError:
            dataset = None

        call_params = dict(params or {})
        ctx = RunContext(
            runtime=self,
            workspace_id=workspace_id,
            dataset=dataset,
            params=call_params,
            extension_storage=storage,
            extension_name=extension_name,
        )
        return record.func(ctx, **call_params)

    def snapshot(self, workspace_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._sync_panel_module_revisions_locked()
            workspace = self.get_workspace(workspace_id)
            return {
                "runtime_id": self.runtime_id,
                "version": self.version,
                "active_workspace_id": self.workspace_registry.active_workspace_id,
                "extensions": [installation.to_dict() for installation in self.list_extensions()],
                "panel_definitions": [
                    definition.to_dict() for definition in self.list_panel_definitions()
                ],
                "tools": [record.to_dict() for record in self.tools.list()],
                "workspaces": [
                    {
                        "id": item.id,
                        "dataset_name": item.dataset_name,
                    }
                    for item in self.workspace_registry.list()
                ],
                "workspace": {
                    "id": workspace.id,
                    "dataset_name": workspace.dataset_name,
                    "collections": [
                        collection.to_dict()
                        for collection in sorted(
                            workspace.collections.values(),
                            key=lambda item: item.id,
                        )
                    ],
                    "ui": {
                        "active_layout_key": workspace.ui.active_layout_key,
                        "selected_ids": list(workspace.ui.selected_ids),
                        "layout_views": {
                            layout_key: view.to_dict()
                            for layout_key, view in sorted(workspace.ui.layout_views.items())
                        },
                        "layout": (
                            _json_object_copy(workspace.ui.layout)
                            if workspace.ui.layout is not None
                            else None
                        ),
                        "layout_revision": workspace.ui.layout_revision,
                        "panels": {
                            panel_id: state.to_dict()
                            for panel_id, state in sorted(workspace.ui.panels.items())
                        },
                        "custom_panels": [
                            _custom_panel_instance_payload(
                                panel,
                                workspace.ui.panels,
                                data=self.get_panel_payload(workspace.id, panel),
                            )
                            for panel in workspace.ui.custom_panels
                        ],
                        "has_explicit_view": workspace.ui.has_explicit_view,
                        "active_panel_id": workspace.ui.active_panel_id,
                        "view_revision": workspace.ui.view_revision,
                    },
                },
            }
