"""Public UI composition helpers for HyperView launch scripts.

The model mirrors Rerun's blueprint split at a small scale: panel definitions
come from built-ins or extensions, while a ``View`` describes concrete panel
instances and how they should be arranged in the workspace.

``Panel`` is the general primitive: it places one instance of any registered
panel type. ``Scatter``, ``Samples``, ``Explorer``, and ``ExtensionPanel`` are
sugar over it for the panel types a script reaches for most often.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from hyperview.runtime import SAMPLES_PANEL_STATE_ID, HyperViewRuntime, PanelInstance

PanelPosition = Literal["center", "right", "bottom"]
PanelDirection = Literal["right", "left", "above", "below", "within"]
ContainerKind = Literal["horizontal", "vertical", "tabs", "grid"]

#: The panel id the workspace's default Samples panel owns.
#:
#: Collection commands with no ``panel_id`` land here, and a panel that wants to
#: read or drive the shared sample view addresses this id. Scripts and demos
#: should use ``hv.ui.SAMPLES_PANEL_ID`` rather than copying the literal.
SAMPLES_PANEL_ID = SAMPLES_PANEL_STATE_ID

SCATTER_PANEL_TYPE = "scatter"
SAMPLES_PANEL_TYPE = "samples"
EXPLORER_PANEL_TYPE = "explorer"


@dataclass(frozen=True)
class PanelLayout:
    """Durable layout hints for a concrete panel instance.

    HyperView stores these as runtime view state and maps them onto the active
    frontend's panel system. They are intentionally not Dockview-specific.
    """

    width: int | None = None
    height: int | None = None
    min_width: int | None = None
    min_height: int | None = None
    max_width: int | None = None
    max_height: int | None = None
    visible: bool = True

    def to_runtime_kwargs(self) -> dict[str, Any]:
        """Return runtime panel fields for this layout."""

        return {
            "width": self.width,
            "height": self.height,
            "min_width": self.min_width,
            "min_height": self.min_height,
            "max_width": self.max_width,
            "max_height": self.max_height,
            "visible": self.visible,
        }


def _clean_props(props: dict[str, Any] | None, typed: dict[str, Any]) -> dict[str, Any]:
    """Merge free-form props with typed keyword props, dropping unset ones.

    Free-form props stay open on purpose: a panel may accept anything its
    renderer understands. Typed keywords are a shortcut for the documented
    props, and win when both name the same prop.
    """

    merged = dict(props or {})
    merged.update({key: value for key, value in typed.items() if value is not None})
    return merged


@dataclass(frozen=True, init=False)
class Panel:
    """One instance of a registered panel type, placed in a view.

    ``panel_type`` is the name the runtime registers a panel under: ``"samples"``,
    ``"scatter"``, and ``"explorer"`` for the built-ins, and for an extension
    panel whatever its manifest declares — ``"<extension>.<panel id>"`` unless
    the manifest sets an explicit ``panel_type``. Applying a view validates
    every panel type, so a typo names itself instead of opening an empty
    workspace.
    """

    panel_type: str
    id: str
    title: str | None = None
    props: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] | None = None
    position: PanelPosition | None = None
    reference_panel_id: str | None = None
    direction: PanelDirection | None = None
    layout: PanelLayout | None = None
    layout_key: str | None = None
    geometry: str | None = None
    layout_dimension: int | None = None

    def __init__(
        self,
        panel_type: str,
        *,
        id: str,
        title: str | None = None,
        props: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
        position: PanelPosition | None = None,
        layout: PanelLayout | None = None,
        reference_panel_id: str | None = None,
        direction: PanelDirection | None = None,
        layout_key: str | None = None,
        geometry: str | None = None,
        layout_dimension: int | None = None,
    ) -> None:
        """Place one panel instance.

        Args:
            panel_type: Registered panel type.
            id: Panel instance id, unique within the view.
            title: Panel title. Defaults to the panel definition's title.
            props: Panel props, passed to the renderer.
            state: The panel's opening runtime state. HyperView applies it when
                the view is applied, on top of the definition's default state,
                so a script does not have to patch panel state afterwards.
            position: ``center``, ``right``, or ``bottom``. Defaults to the
                panel definition's own default placement.
            layout: Size hints, as a :class:`PanelLayout`.
            reference_panel_id: Panel this one is placed relative to.
            direction: Where to place it relative to ``reference_panel_id``.
            layout_key: For scatter panels, the layout to pin the panel to.
            geometry: For scatter panels, the layout geometry.
            layout_dimension: For scatter panels, 2 or 3.
        """

        setter = object.__setattr__
        setter(self, "panel_type", panel_type)
        setter(self, "id", id)
        setter(self, "title", title)
        setter(self, "props", dict(props or {}))
        setter(self, "state", dict(state) if state is not None else None)
        setter(self, "position", position)
        setter(self, "reference_panel_id", reference_panel_id)
        setter(self, "direction", direction)
        setter(self, "layout", layout)
        setter(self, "layout_key", layout_key)
        setter(self, "geometry", geometry)
        setter(self, "layout_dimension", layout_dimension)


@dataclass(frozen=True, init=False)
class ExtensionPanel(Panel):
    """A panel instance backed by an installed extension panel asset.

    ``ExtensionPanel(extension="x", panel="y")`` is
    ``Panel(panel_type="x.y")`` for an extension whose manifest does not
    override ``panel_type``. The extension must be registered before the view
    is applied; see ``hv.launch(..., extensions=[...])``.
    """

    extension: str = ""
    panel: str = ""

    def __init__(
        self,
        id: str,
        extension: str,
        panel: str,
        title: str | None = None,
        position: PanelPosition | None = None,
        reference_panel_id: str | None = None,
        direction: PanelDirection | None = None,
        layout: PanelLayout | None = None,
        props: dict[str, Any] | None = None,
        *,
        state: dict[str, Any] | None = None,
    ) -> None:
        Panel.__init__(
            self,
            f"{extension}.{panel}",
            id=id,
            title=title,
            props=props,
            state=state,
            position=position,
            layout=layout,
            reference_panel_id=reference_panel_id,
            direction=direction,
        )
        object.__setattr__(self, "extension", extension)
        object.__setattr__(self, "panel", panel)


@dataclass(frozen=True, init=False)
class Scatter(Panel):
    """A scatter panel instance pinned to an explicit layout."""

    def __init__(
        self,
        id: str,
        title: str = "Embeddings",
        layout_key: str | None = None,
        position: PanelPosition = "center",
        reference_panel_id: str | None = None,
        direction: PanelDirection | None = None,
        geometry: str | None = None,
        layout_dimension: int | None = None,
        layout: PanelLayout | None = None,
        props: dict[str, Any] | None = None,
        *,
        state: dict[str, Any] | None = None,
        preset: str | None = None,
        presets: dict[str, Any] | None = None,
    ) -> None:
        Panel.__init__(
            self,
            SCATTER_PANEL_TYPE,
            id=id,
            title=title,
            props=_clean_props(props, {"preset": preset, "presets": presets}),
            state=state,
            position=position,
            layout=layout,
            reference_panel_id=reference_panel_id,
            direction=direction,
            layout_key=layout_key,
            geometry=geometry,
            layout_dimension=layout_dimension,
        )


@dataclass(frozen=True, init=False)
class Samples(Panel):
    """A built-in samples panel instance.

    The documented props have keyword parameters. ``mode`` chooses how the
    panel reads its rows: ``auto`` follows runtime state, ``results`` shows a
    prepared collection in its authored order, ``ranked`` shows nearest
    neighbours of ``rank["anchor_sample_id"]``, and ``browse`` stays on the
    dataset. Anything not covered here can still be passed through ``props``.
    """

    def __init__(
        self,
        id: str = "samples",
        title: str = "Samples",
        position: PanelPosition = "right",
        reference_panel_id: str | None = None,
        direction: PanelDirection | None = None,
        layout: PanelLayout | None = None,
        props: dict[str, Any] | None = None,
        *,
        state: dict[str, Any] | None = None,
        mode: Literal["auto", "browse", "ranked", "results"] | None = None,
        collection_id: str | None = None,
        anchor_sample_id: str | None = None,
        label_field: str | None = None,
        show_text_search: bool | None = None,
        rank: dict[str, Any] | None = None,
    ) -> None:
        Panel.__init__(
            self,
            SAMPLES_PANEL_TYPE,
            id=id,
            title=title,
            props=_clean_props(
                props,
                {
                    "mode": mode,
                    "collectionId": collection_id,
                    "anchorSampleId": anchor_sample_id,
                    "labelField": label_field,
                    "showTextSearch": show_text_search,
                    "rank": _samples_rank_props(rank),
                },
            ),
            state=state,
            position=position,
            layout=layout,
            reference_panel_id=reference_panel_id,
            direction=direction,
        )


@dataclass(frozen=True, init=False)
class Explorer(Panel):
    """A built-in explorer panel instance: labels and dataset facets."""

    def __init__(
        self,
        id: str = "explorer",
        title: str = "Labels",
        position: PanelPosition = "right",
        reference_panel_id: str | None = None,
        direction: PanelDirection | None = None,
        layout: PanelLayout | None = None,
        props: dict[str, Any] | None = None,
        *,
        state: dict[str, Any] | None = None,
    ) -> None:
        Panel.__init__(
            self,
            EXPLORER_PANEL_TYPE,
            id=id,
            title=title,
            props=props,
            state=state,
            position=position,
            layout=layout,
            reference_panel_id=reference_panel_id,
            direction=direction,
        )


_SAMPLES_RANK_PROP_NAMES = {
    "anchor_sample_id": "anchorSampleId",
    "layout_key": "layoutKey",
    "space_key": "spaceKey",
    "show_distance": "showDistance",
}


def _samples_rank_props(rank: dict[str, Any] | None) -> dict[str, Any] | None:
    """Accept snake_case rank keys and hand the panel the camelCase it reads."""

    if rank is None:
        return None
    return {_SAMPLES_RANK_PROP_NAMES.get(key, key): value for key, value in rank.items()}


@dataclass(frozen=True)
class Container:
    """A container that composes panel instances."""

    kind: ContainerKind
    contents: tuple[Panel | Container, ...]
    shares: tuple[float, ...] | None = None
    active_tab: int | str | None = None


@dataclass(frozen=True, init=False)
class View:
    """A concrete workspace view made of panel instances and containers."""

    contents: tuple[Panel | Container, ...]
    clear_existing: bool = True
    active_panel: str | None = None

    def __init__(
        self,
        *contents: Panel | Container,
        clear_existing: bool = True,
        active_panel: str | None = None,
    ) -> None:
        object.__setattr__(self, "contents", tuple(contents))
        object.__setattr__(self, "clear_existing", clear_existing)
        object.__setattr__(self, "active_panel", active_panel)

    def apply(self, runtime: HyperViewRuntime, workspace_id: str) -> None:
        """Apply this view to a runtime workspace."""

        panels = compile_view(self, runtime=runtime, workspace_id=workspace_id)
        initial_states = collect_initial_panel_states(self)
        if self.clear_existing:
            runtime.replace_custom_panels(
                workspace_id,
                panels,
                bump_view_revision=True,
                has_explicit_view=True,
                active_panel_id=self.active_panel,
                initial_panel_states=initial_states,
            )
            return

        for panel in panels:
            runtime.add_custom_panel(
                workspace_id,
                panel,
                initial_state=initial_states.get(panel.id),
            )


def Horizontal(  # noqa: N802 - public UI helper mirrors component naming.
    *contents: Panel | Container,
    shares: list[float] | tuple[float, ...] | None = None,
) -> Container:
    return Container(
        kind="horizontal", contents=tuple(contents), shares=tuple(shares) if shares else None
    )


def Vertical(  # noqa: N802 - public UI helper mirrors component naming.
    *contents: Panel | Container,
    shares: list[float] | tuple[float, ...] | None = None,
) -> Container:
    return Container(
        kind="vertical", contents=tuple(contents), shares=tuple(shares) if shares else None
    )


def Tabs(  # noqa: N802 - public UI helper mirrors component naming.
    *contents: Panel | Container,
    active_tab: int | str | None = None,
) -> Container:
    return Container(kind="tabs", contents=tuple(contents), active_tab=active_tab)


def Grid(  # noqa: N802 - public UI helper mirrors component naming.
    *contents: Panel | Container,
    shares: list[float] | tuple[float, ...] | None = None,
) -> Container:
    return Container(
        kind="grid", contents=tuple(contents), shares=tuple(shares) if shares else None
    )


def iter_view_panels(item: View | Container | Panel) -> list[Panel]:
    """Return every panel instance in a view, container, or panel, in order."""

    if isinstance(item, Panel):
        return [item]
    contents = item.contents
    panels: list[Panel] = []
    for child in contents:
        panels.extend(iter_view_panels(child))
    return panels


def collect_initial_panel_states(view: View) -> dict[str, dict[str, Any]]:
    """Return the opening state each panel in the view declares."""

    return {
        panel.id: dict(panel.state)
        for panel in iter_view_panels(view)
        if panel.state is not None
    }


def _resolve_panel(panel: Panel, runtime: HyperViewRuntime):
    """Resolve one view panel against the runtime's registered panel definitions.

    ``ExtensionPanel`` names its panel by extension and manifest id, which stays
    correct even when the manifest overrides ``panel_type``. Everything else
    resolves by panel type.
    """

    if isinstance(panel, ExtensionPanel):
        return runtime.find_extension_panel(panel.extension, panel.panel)
    return runtime.find_panel_type(panel.panel_type)


def _unknown_panel_type_error(panel: Panel, runtime: HyperViewRuntime) -> ValueError:
    registered = ", ".join(runtime.list_panel_types()) or "(none)"
    if isinstance(panel, ExtensionPanel):
        requested = f"extension {panel.extension!r} panel {panel.panel!r}"
    else:
        requested = f"panel type {panel.panel_type!r}"
    return ValueError(
        f"Unknown {requested} for view panel {panel.id!r}. "
        f"Registered panel types: {registered}. "
        "Extension panel types only exist once the extension is registered, so "
        "register it before applying the view — hv.launch(..., extensions=[...]) "
        "or session.ui.apply_view(view, extensions=[...])."
    )


def validate_panel_types(view: View, runtime: HyperViewRuntime) -> None:
    """Fail with a readable error when a view names a panel type nothing registers."""

    for panel in iter_view_panels(view):
        if _resolve_panel(panel, runtime) is None:
            raise _unknown_panel_type_error(panel, runtime)


def compile_view(
    view: View,
    *,
    runtime: HyperViewRuntime | None = None,
    workspace_id: str | None = None,
) -> list[PanelInstance]:
    """Compile a public view object into runtime panel specs."""

    if runtime is not None:
        validate_panel_types(view, runtime)

    specs: list[PanelInstance] = []
    for item in view.contents:
        specs.extend(
            _compile_item(
                item,
                default_position=None,
                reference_panel_id=None,
                direction=None,
                runtime=runtime,
                workspace_id=workspace_id,
            )
        )
    _validate_unique_panel_ids(specs)
    return specs


def _validate_unique_panel_ids(panels: list[PanelInstance]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for panel in panels:
        if panel.id in seen and panel.id not in duplicates:
            duplicates.append(panel.id)
        seen.add(panel.id)
    if duplicates:
        duplicate_list = ", ".join(repr(panel_id) for panel_id in duplicates)
        raise ValueError(
            "View panel ids must be unique. Duplicate panel id(s): "
            f"{duplicate_list}. Pass an explicit id when reusing a panel type."
        )


def _compile_item(
    item: Panel | Container,
    *,
    default_position: PanelPosition | None,
    reference_panel_id: str | None,
    direction: PanelDirection | None,
    runtime: HyperViewRuntime | None,
    workspace_id: str | None,
) -> list[PanelInstance]:
    if isinstance(item, Container):
        return _compile_container(
            item,
            default_position=default_position,
            reference_panel_id=reference_panel_id,
            direction=direction,
            runtime=runtime,
            workspace_id=workspace_id,
        )

    position = default_position if default_position is not None else item.position
    spec = _panel_to_spec(
        item,
        position=position,
        runtime=runtime,
        workspace_id=workspace_id,
    )
    if reference_panel_id is not None:
        spec.reference_panel_id = reference_panel_id
    if direction is not None:
        spec.direction = direction
    return [spec]


def _compile_container(
    container: Container,
    *,
    default_position: PanelPosition | None,
    reference_panel_id: str | None,
    direction: PanelDirection | None,
    runtime: HyperViewRuntime | None,
    workspace_id: str | None,
) -> list[PanelInstance]:
    specs: list[PanelInstance] = []
    previous_panel_id: str | None = None
    child_direction = _container_direction(container.kind)

    for child in container.contents:
        child_specs = _compile_item(
            child,
            default_position=default_position or "center",
            reference_panel_id=previous_panel_id or reference_panel_id,
            direction=(
                child_direction
                if previous_panel_id is not None
                else direction if reference_panel_id is not None else None
            ),
            runtime=runtime,
            workspace_id=workspace_id,
        )
        specs.extend(child_specs)
        if child_specs:
            previous_panel_id = child_specs[0].id

    if container.kind == "tabs" and specs:
        active_tab = container.active_tab
        if active_tab is None:
            active_index = 0
        elif isinstance(active_tab, int):
            if active_tab < 0 or active_tab >= len(specs):
                raise ValueError(
                    f"Tabs active_tab index {active_tab} is outside 0..{len(specs) - 1}"
                )
            active_index = active_tab
        else:
            active_index = next(
                (index for index, spec in enumerate(specs) if spec.id == active_tab),
                -1,
            )
            if active_index < 0:
                raise ValueError(f"Tabs active_tab panel id is not in the container: {active_tab}")
        specs[active_index].active = True

    return specs


def _container_direction(kind: ContainerKind) -> PanelDirection:
    if kind == "vertical":
        return "below"
    if kind == "tabs":
        return "within"
    return "right"


def _panel_to_spec(
    panel: Panel,
    *,
    position: PanelPosition | None,
    runtime: HyperViewRuntime | None,
    workspace_id: str | None,
) -> PanelInstance:
    layout_kwargs = panel.layout.to_runtime_kwargs() if panel.layout is not None else {}

    if runtime is not None:
        match = _resolve_panel(panel, runtime)
        if match is None:
            raise _unknown_panel_type_error(panel, runtime)

        if match.extension is not None:
            return runtime.build_custom_panel(
                workspace_id or "",
                panel_id=panel.id,
                title=panel.title,
                extension=match.extension,
                extension_panel=match.extension_panel,
                position=position,
                reference_panel_id=panel.reference_panel_id,
                direction=panel.direction,
                props=panel.props,
                **layout_kwargs,
            )

        if panel.panel_type == SCATTER_PANEL_TYPE and panel.layout_key:
            return runtime.build_custom_panel(
                workspace_id or "",
                panel_id=panel.id,
                title=panel.title or match.definition.title or match.definition.label,
                layout_key=panel.layout_key,
                position=position,
                reference_panel_id=panel.reference_panel_id,
                direction=panel.direction,
                props=panel.props,
                geometry=panel.geometry,
                layout_dimension=panel.layout_dimension,
                require_resolved_layout=False,
                **layout_kwargs,
            )

        return runtime.build_custom_panel(
            workspace_id or "",
            panel_id=panel.id,
            title=panel.title,
            builtin_panel=panel.panel_type,
            position=position,
            reference_panel_id=panel.reference_panel_id,
            direction=panel.direction,
            props=panel.props,
            **layout_kwargs,
        )

    # Without a runtime we can only describe built-in panels: an extension
    # panel's module file lives in the installed extension.
    if panel.panel_type not in {SCATTER_PANEL_TYPE, SAMPLES_PANEL_TYPE, EXPLORER_PANEL_TYPE}:
        raise ValueError(
            f"Panel type {panel.panel_type!r} requires a runtime to resolve its panel definition"
        )

    return PanelInstance(
        id=panel.id,
        title=panel.title or panel.panel_type.title(),
        panel_type=panel.panel_type,
        builtin_panel=panel.panel_type,
        position=position or "right",
        layout_key=panel.layout_key,
        geometry=panel.geometry,
        layout_dimension=panel.layout_dimension,
        reference_panel_id=panel.reference_panel_id,
        direction=panel.direction,
        props=dict(panel.props),
        **layout_kwargs,
    )


__all__ = [
    "SAMPLES_PANEL_ID",
    "Container",
    "Explorer",
    "ExtensionPanel",
    "Grid",
    "Horizontal",
    "Panel",
    "PanelLayout",
    "Samples",
    "Scatter",
    "Tabs",
    "Vertical",
    "View",
    "collect_initial_panel_states",
    "compile_view",
    "iter_view_panels",
    "validate_panel_types",
]
