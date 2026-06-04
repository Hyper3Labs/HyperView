"""Public UI composition helpers for HyperView launch scripts.

The model mirrors Rerun's blueprint split at a small scale: panel definitions
come from built-ins or extensions, while a ``View`` describes concrete panel
instances and how they should be arranged in the workspace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from hyperview.extensions import resolve_panel_source
from hyperview.runtime import CustomPanelSpec, HyperViewRuntime

PanelPosition = Literal["center", "right", "bottom"]
PanelDirection = Literal["right", "left", "above", "below", "within"]
ContainerKind = Literal["horizontal", "vertical", "tabs", "grid"]


@dataclass(frozen=True)
class ExtensionPanel:
    """A module panel instance backed by an installed extension panel asset."""

    id: str
    extension: str
    panel: str
    title: str | None = None
    position: PanelPosition = "right"
    reference_panel_id: str | None = None
    direction: PanelDirection | None = None
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scatter:
    """A scatter panel instance pinned to an explicit layout."""

    id: str
    title: str
    layout_key: str
    position: PanelPosition = "center"
    reference_panel_id: str | None = None
    direction: PanelDirection | None = None
    geometry: str | None = None
    layout_dimension: int | None = None
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Container:
    """A container that composes panel instances."""

    kind: ContainerKind
    contents: tuple[ExtensionPanel | Scatter | Container, ...]
    shares: tuple[float, ...] | None = None
    active_tab: int | str | None = None


@dataclass(frozen=True, init=False)
class View:
    """A concrete workspace view made of panel instances and containers."""

    contents: tuple[ExtensionPanel | Scatter | Container, ...]
    clear_existing: bool = True

    def __init__(
        self,
        *contents: ExtensionPanel | Scatter | Container,
        clear_existing: bool = True,
    ) -> None:
        object.__setattr__(self, "contents", tuple(contents))
        object.__setattr__(self, "clear_existing", clear_existing)

    def apply(self, runtime: HyperViewRuntime, workspace_id: str) -> None:
        """Apply this view to a runtime workspace."""

        panels = compile_view(self, runtime=runtime)
        if self.clear_existing:
            runtime.replace_custom_panels(workspace_id, panels, bump_view_revision=True)
            return

        for panel in panels:
            runtime.add_custom_panel(workspace_id, panel)


def Horizontal(  # noqa: N802 - public UI helper mirrors component naming.
    *contents: ExtensionPanel | Scatter | Container,
    shares: list[float] | tuple[float, ...] | None = None,
) -> Container:
    return Container(kind="horizontal", contents=tuple(contents), shares=tuple(shares) if shares else None)


def Vertical(  # noqa: N802 - public UI helper mirrors component naming.
    *contents: ExtensionPanel | Scatter | Container,
    shares: list[float] | tuple[float, ...] | None = None,
) -> Container:
    return Container(kind="vertical", contents=tuple(contents), shares=tuple(shares) if shares else None)


def Tabs(  # noqa: N802 - public UI helper mirrors component naming.
    *contents: ExtensionPanel | Scatter | Container,
    active_tab: int | str | None = None,
) -> Container:
    return Container(kind="tabs", contents=tuple(contents), active_tab=active_tab)


def Grid(  # noqa: N802 - public UI helper mirrors component naming.
    *contents: ExtensionPanel | Scatter | Container,
    shares: list[float] | tuple[float, ...] | None = None,
) -> Container:
    return Container(kind="grid", contents=tuple(contents), shares=tuple(shares) if shares else None)


def compile_view(view: View, *, runtime: HyperViewRuntime | None = None) -> list[CustomPanelSpec]:
    """Compile a public view object into runtime panel specs."""

    specs: list[CustomPanelSpec] = []
    for item in view.contents:
        specs.extend(
            _compile_item(
                item,
                default_position=None,
                reference_panel_id=None,
                direction=None,
                runtime=runtime,
            )
        )
    return specs


def _compile_item(
    item: ExtensionPanel | Scatter | Container,
    *,
    default_position: PanelPosition | None,
    reference_panel_id: str | None,
    direction: PanelDirection | None,
    runtime: HyperViewRuntime | None,
) -> list[CustomPanelSpec]:
    if isinstance(item, Container):
        return _compile_container(item, default_position=default_position, runtime=runtime)

    position = default_position or item.position
    spec = _panel_to_spec(item, position=position, runtime=runtime)
    if reference_panel_id is not None:
        spec.reference_panel_id = reference_panel_id
    if direction is not None:
        spec.direction = direction
    return [spec]


def _compile_container(
    container: Container,
    *,
    default_position: PanelPosition | None,
    runtime: HyperViewRuntime | None,
) -> list[CustomPanelSpec]:
    specs: list[CustomPanelSpec] = []
    previous_panel_id: str | None = None
    child_direction = _container_direction(container.kind)

    for child in container.contents:
        child_specs = _compile_item(
            child,
            default_position=default_position or "center",
            reference_panel_id=previous_panel_id,
            direction=child_direction if previous_panel_id is not None else None,
            runtime=runtime,
        )
        specs.extend(child_specs)
        if child_specs:
            previous_panel_id = child_specs[0].id

    return specs


def _container_direction(kind: ContainerKind) -> PanelDirection:
    if kind == "vertical":
        return "below"
    if kind == "tabs":
        return "within"
    return "right"


def _panel_to_spec(
    panel: ExtensionPanel | Scatter,
    *,
    position: PanelPosition,
    runtime: HyperViewRuntime | None,
) -> CustomPanelSpec:
    if isinstance(panel, Scatter):
        return CustomPanelSpec(
            id=panel.id,
            title=panel.title,
            kind="scatter",
            position=position,
            layout_key=panel.layout_key,
            geometry=panel.geometry,
            layout_dimension=panel.layout_dimension,
            reference_panel_id=panel.reference_panel_id,
            direction=panel.direction,
            props=dict(panel.props),
        )

    if isinstance(panel, ExtensionPanel):
        if runtime is None:
            raise ValueError("ExtensionPanel requires a runtime to resolve its module file")
        installation = runtime.get_extension(panel.extension)
        if installation is None:
            raise ValueError(f"Unknown extension: {panel.extension}")

        manifest_panel = next(
            (entry for entry in installation.manifest.panels if entry.id == panel.panel),
            None,
        )
        if manifest_panel is None:
            raise ValueError(
                f"Extension '{panel.extension}' has no panel '{panel.panel}'"
            )

        module_file = resolve_panel_source(
            installation.manifest.folder,
            manifest_panel.file,
        )
        return CustomPanelSpec(
            id=panel.id,
            title=panel.title or manifest_panel.title,
            kind="module",
            extension=panel.extension,
            extension_panel=panel.panel,
            module_file=str(module_file),
            position=position,
            reference_panel_id=panel.reference_panel_id,
            direction=panel.direction,
            props=dict(panel.props),
        )

    raise TypeError(f"Unsupported panel type: {type(panel).__name__}")


__all__ = [
    "Container",
    "ExtensionPanel",
    "Grid",
    "Horizontal",
    "Scatter",
    "Tabs",
    "Vertical",
    "View",
    "compile_view",
]
