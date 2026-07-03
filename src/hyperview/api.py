"""Public API for HyperView."""

import json
import os
import socket
import threading
import time
import webbrowser
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import uvicorn

import hyperview.ui as ui_module
from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry
from hyperview.core.dataset import Dataset
from hyperview.runtime import HyperViewRuntime, ProviderRegistry
from hyperview.server.app import create_app, set_runtime

__all__ = ["Dataset", "launch", "Session", "register_provider", "unregister_provider"]


@dataclass(frozen=True)
class _HealthResponse:
    name: str | None
    session_id: str | None
    workspace_id: str | None
    dataset: str | None
    pid: int | None


def _can_connect(host: str, port: int, timeout_s: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _try_read_health(url: str, timeout_s: float) -> _HealthResponse | None:
    try:
        return _read_health(url, timeout_s=timeout_s)
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return None


def _read_health(url: str, timeout_s: float) -> _HealthResponse:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout_s) as response:
        data = json.loads(response.read().decode("utf-8"))

    return _HealthResponse(
        name=data.get("name"),
        session_id=data.get("session_id"),
        workspace_id=data.get("workspace_id"),
        dataset=data.get("dataset"),
        pid=data.get("pid") if isinstance(data.get("pid"), int) else None,
    )


def _resolve_default_launch_layout(dataset: Dataset) -> str:
    spaces = dataset.list_spaces()

    if any(space.geometry not in ("hyperboloid", "hypersphere") for space in spaces):
        return "euclidean:2d"
    if any(space.geometry == "hypersphere" for space in spaces):
        return "spherical:3d"
    return "poincare:2d"


def register_provider(
    alias: str,
    import_path: str,
    *,
    description: str | None = None,
    defaults: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Register a custom Python embedding provider.

    Built-in providers such as ``embed-anything`` and ``hyper-models`` do not
    need registration. Use this only for project-local providers that are not
    already available through HyperView's provider catalog.
    """

    registration = ProviderRegistry().register_python(
        alias,
        import_path,
        description=description,
        defaults=defaults,
        overwrite=overwrite,
    )
    return registration.to_dict()


def unregister_provider(alias: str) -> bool:
    """Remove a custom Python embedding provider registration."""

    return ProviderRegistry().unregister(alias)


class Session:
    """A session for the HyperView visualizer."""

    def __init__(
        self,
        runtime: HyperViewRuntime,
        host: str,
        port: int,
        dataset: Dataset | None = None,
        controls_runtime: bool = True,
    ):
        self.runtime = runtime
        self.dataset = dataset
        self.host = host
        self.port = port
        self._controls_runtime = controls_runtime
        # Prefer a browser-connectable host for user-facing URLs.
        # When binding to 0.0.0.0, users should connect via 127.0.0.1 locally.
        self.url = f"http://{self._connect_host}:{port}"
        self._server_thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._startup_error: BaseException | None = None
        self.session_id = uuid4().hex
        self._control_registry = create_default_command_registry()
        self._control_service: ControlService | None = None
        self.control = SessionControlController(self)
        self.ui = SessionUiController(self)

    @property
    def _connect_host(self) -> str:
        return "127.0.0.1" if self.host == "0.0.0.0" else self.host

    @property
    def _health_url(self) -> str:
        return f"http://{self._connect_host}:{self.port}/__hyperview__/health"

    def _run_server(self):
        try:
            set_runtime(self.runtime)
            app = create_app(runtime=self.runtime, session_id=self.session_id)
            config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
            self._server = uvicorn.Server(config)
            self._server.run()
        except BaseException as exc:
            self._startup_error = exc

    def start(self, background: bool = True):
        """Start the visualizer server."""
        if not background:
            self._run_server()
            return

        # Fail fast if something is already listening on this port.
        if _can_connect(self._connect_host, self.port, timeout_s=0.2):
            health = _try_read_health(self._health_url, timeout_s=0.2)
            if health is not None and health.name == "hyperview":
                raise RuntimeError(
                    "HyperView failed to start because the port is already serving "
                    f"HyperView (port={self.port}, session_id={health.session_id}). "
                    "Choose a different port or stop the existing server."
                )

            raise RuntimeError(
                "HyperView failed to start because the port is already in use "
                f"by a non-HyperView service (port={self.port}). Choose a different "
                "port or stop the process listening on that port."
            )

        self._startup_error = None
        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()

        deadline = time.time() + 5.0
        last_health_error: Exception | None = None

        while time.time() < deadline:
            if self._startup_error is not None:
                raise RuntimeError(
                    f"HyperView server failed to start (port={self.port}): "
                    f"{type(self._startup_error).__name__}: {self._startup_error}"
                )

            if self._server_thread is not None and not self._server_thread.is_alive():
                raise RuntimeError(
                    "HyperView server thread exited during startup. "
                    f"The port may be in use (port={self.port})."
                )

            try:
                health = _read_health(self._health_url, timeout_s=0.2)
            except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                last_health_error = exc
                time.sleep(0.05)
                continue

            if health.name == "hyperview" and health.session_id == self.session_id:
                return

            if health.name == "hyperview":
                raise RuntimeError(
                    "HyperView failed to start because the port is already serving "
                    f"a different HyperView session (port={self.port}, "
                    f"session_id={health.session_id})."
                )

            raise RuntimeError(
                "HyperView failed to start because the port is already serving "
                f"a non-HyperView app (port={self.port})."
            )

        raise TimeoutError(
            "HyperView server did not become ready in time "
            f"(port={self.port}). Last error: {last_health_error}"
        )

    def stop(self):
        """Stop the visualizer server."""
        if self._server:
            self._server.should_exit = True

    def join(self, timeout: float | None = None) -> None:
        """Wait for the background server thread to exit."""

        if self._server_thread is not None:
            self._server_thread.join(timeout=timeout)

    def wait(self, poll_interval: float = 0.25) -> None:
        """Keep the session alive until interrupted or the server exits."""

        try:
            while True:
                time.sleep(poll_interval)
                if self._server_thread is not None and not self._server_thread.is_alive():
                    raise RuntimeError("HyperView server stopped unexpectedly.")
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
            self.join(timeout=2.0)

    def show(self, height: int = 800):
        """Display the visualizer in a notebook.

        In Google Colab, notebook kernels cannot be accessed via localhost.
        Colab exposes kernel ports through a proxy URL (see
        `google.colab.kernel.proxyPort`). This renders a link to the proxied URL
        that opens in a new tab.

        In other notebook environments, it renders a clickable link to the local
        URL and a best-effort JavaScript auto-open.
        """
        if _is_colab():
            try:
                from google.colab.output import eval_js  # type: ignore[import-not-found]
                from IPython.display import HTML, display

                proxy_url = eval_js(f"google.colab.kernel.proxyPort({self.port})")
                app_url = str(proxy_url).rstrip("/") + "/"

                display(
                    HTML(
                        "<p>HyperView is running in Colab. "
                        f"<a href=\"{app_url}\" target=\"_blank\" rel=\"noopener noreferrer\">"
                        "Open HyperView in a new tab</a>.</p>"
                    )
                )
                display(HTML(f"<p style=\"font-size:12px;color:#666;\">{app_url}</p>"))
                return
            except Exception:
                # Fall through to the generic notebook behavior.
                pass

        # Default: open in a new browser tab (works well for Jupyter).
        try:
            from IPython.display import HTML, Javascript, display

            display(
                HTML(
                    "<p>HyperView is running. "
                    f"<a href=\"{self.url}\" target=\"_blank\" rel=\"noopener\">Open in a new tab</a>."
                    "</p>"
                )
            )

            # Best-effort auto-open. Some browsers may block popups.
            display(Javascript(f'window.open("{self.url}", "_blank");'))
        except ImportError:
            print(f"IPython not installed. Please visit {self.url} in your browser.")

    def open_browser(self):
        """Open the visualizer in a browser window."""
        webbrowser.open(self.url)


class SessionControlController:
    """Generic command runner for a HyperView session."""

    def __init__(self, session: Session):
        self._session = session

    def _service(self) -> ControlService:
        if not self._session._controls_runtime:
            raise RuntimeError(
                "This session is attached to an existing HyperView server. "
                "session.control can only mutate sessions started by this process; "
                "use the control-plane CLI/API or launch with reuse_server=False."
            )
        if self._session._control_service is None:
            self._session._control_service = ControlService(
                self._session.runtime,
                self._session._control_registry,
            )
        return self._session._control_service

    def run(
        self,
        command: str,
        *,
        target: dict[str, Any] | None = None,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a backend-owned control command and return the result envelope."""

        result = self._service().run(
            CommandEnvelope(
                command=command,
                target=target or {},
                args=args or {},
            )
        )
        payload = result.to_dict()
        if not result.ok:
            error = result.error
            if error is None:
                raise RuntimeError("Command failed")
            raise RuntimeError(f"{error.code}: {error.message}")
        return payload


class SessionUiController:
    """Public UI control surface for a HyperView session."""

    def __init__(self, session: Session):
        self._session = session

    def _runtime(self) -> HyperViewRuntime:
        if not self._session._controls_runtime:
            raise RuntimeError(
                "This session is attached to an existing HyperView server. "
                "session.ui can only mutate sessions started by this process; "
                "use the control-plane CLI/API or launch with reuse_server=False."
            )
        return self._session.runtime

    def apply_view(self, view: ui_module.View, *, workspace_id: str = "default") -> None:
        """Apply a Rerun-style view composition to a workspace."""

        view.apply(self._runtime(), workspace_id)

    def add_scatter(
        self,
        *,
        panel_id: str,
        title: str,
        layout_key: str,
        workspace_id: str = "default",
        position: ui_module.PanelPosition = "center",
        reference_panel_id: str | None = None,
        direction: ui_module.PanelDirection | None = None,
        geometry: str | None = None,
        layout_dimension: int | None = None,
        layout: ui_module.PanelLayout | None = None,
        props: dict[str, object] | None = None,
    ) -> None:
        """Add a scatter panel pinned to an explicit layout."""

        self._session.control.run(
            "ui.panel.add",
            target={"workspace_id": workspace_id},
            args={
                "panel_id": panel_id,
                "title": title,
                "kind": "scatter",
                "layout_key": layout_key,
                "position": position,
                "reference_panel_id": reference_panel_id,
                "direction": direction,
                "geometry": geometry,
                "layout_dimension": layout_dimension,
                "props": dict(props or {}),
                **(layout.to_runtime_kwargs() if layout is not None else {}),
                "require_resolved_layout": False,
            },
        )

    def update_panel(
        self,
        panel_id: str,
        *,
        workspace_id: str = "default",
        title: str | None = None,
        position: ui_module.PanelPosition | None = None,
        reference_panel_id: str | None = None,
        direction: ui_module.PanelDirection | None = None,
        layout: ui_module.PanelLayout | None = None,
        visible: bool | None = None,
        active: bool | None = None,
        props: dict[str, object] | None = None,
    ) -> None:
        """Update a runtime panel's durable view/layout state."""

        layout_kwargs = (
            {
                key: value
                for key, value in layout.to_runtime_kwargs().items()
                if value is not None
            }
            if layout is not None
            else {}
        )
        if visible is not None:
            layout_kwargs["visible"] = visible
        placement_kwargs: dict[str, object | None] = {}
        if position is not None or reference_panel_id is not None:
            placement_kwargs["reference_panel_id"] = reference_panel_id
        if position is not None or direction is not None:
            placement_kwargs["direction"] = direction
        update_args: dict[str, object | None] = {
            **placement_kwargs,
            **layout_kwargs,
        }
        if title is not None:
            update_args["title"] = title
        if position is not None:
            update_args["position"] = position
        if active is not None:
            update_args["active"] = active
        if props is not None:
            update_args["props"] = dict(props)
        self._session.control.run(
            "ui.panel.update",
            target={"workspace_id": workspace_id, "panel_id": panel_id},
            args=update_args,
        )

    def resize_panel(
        self,
        panel_id: str,
        *,
        workspace_id: str = "default",
        width: int | None = None,
        height: int | None = None,
        min_width: int | None = None,
        min_height: int | None = None,
        max_width: int | None = None,
        max_height: int | None = None,
    ) -> None:
        """Set durable panel dimensions and constraints."""

        layout_kwargs = {
            key: value
            for key, value in {
                "width": width,
                "height": height,
                "min_width": min_width,
                "min_height": min_height,
                "max_width": max_width,
                "max_height": max_height,
            }.items()
            if value is not None
        }
        self._session.control.run(
            "ui.panel.resize",
            target={"workspace_id": workspace_id, "panel_id": panel_id},
            args=layout_kwargs,
        )

    def move_panel(
        self,
        panel_id: str,
        *,
        workspace_id: str = "default",
        position: ui_module.PanelPosition,
        reference_panel_id: str | None = None,
        direction: ui_module.PanelDirection | None = None,
    ) -> None:
        """Move a panel in the durable workspace view."""

        self._session.control.run(
            "ui.panel.move",
            target={"workspace_id": workspace_id, "panel_id": panel_id},
            args={
                "position": position,
                "reference_panel_id": reference_panel_id,
                "direction": direction,
            },
        )

    def focus_panel(self, panel_id: str, *, workspace_id: str = "default") -> None:
        """Set the active panel for the workspace view."""

        self._session.control.run(
            "ui.panel.focus",
            target={"workspace_id": workspace_id, "panel_id": panel_id},
        )

    def close_panel(self, panel_id: str, *, workspace_id: str = "default") -> None:
        """Hide a panel without deleting it from the workspace view."""

        self._session.control.run(
            "ui.panel.close",
            target={"workspace_id": workspace_id, "panel_id": panel_id},
        )

    def show_panel(self, panel_id: str, *, workspace_id: str = "default") -> None:
        """Show a panel that was hidden in the workspace view."""

        self._session.control.run(
            "ui.panel.show",
            target={"workspace_id": workspace_id, "panel_id": panel_id},
        )

    def get_panel_state(
        self,
        panel_id: str,
        *,
        workspace_id: str = "default",
    ) -> dict[str, object]:
        """Return durable runtime-managed state for a panel."""

        payload = self._session.control.run(
            "ui.panel.state.get",
            target={"workspace_id": workspace_id, "panel_id": panel_id},
        )
        return dict(payload.get("result") or {})

    def patch_panel_state(
        self,
        panel_id: str,
        state: dict[str, object],
        *,
        workspace_id: str = "default",
        replace_state: bool = False,
        expected_revision: int | None = None,
    ) -> dict[str, object]:
        """Patch durable runtime-managed panel state."""

        payload = self._session.control.run(
            "ui.panel.state.patch",
            target={"workspace_id": workspace_id, "panel_id": panel_id},
            args={
                "state": dict(state),
                "replace_state": replace_state,
                "expected_revision": expected_revision,
            },
        )
        return dict(payload.get("result") or {})

    def remove_panel(self, panel_id: str, *, workspace_id: str = "default") -> None:
        self._session.control.run(
            "ui.panel.remove",
            target={"workspace_id": workspace_id, "panel_id": panel_id},
        )

    def set_active_layout(
        self,
        layout_key: str | None,
        *,
        workspace_id: str = "default",
    ) -> None:
        """Set the workspace's active layout."""

        self._runtime().set_active_layout(workspace_id, layout_key)

    def set_selection(
        self,
        sample_ids: Iterable[str],
        *,
        workspace_id: str = "default",
    ) -> None:
        """Set the workspace's selected sample ids."""

        self._runtime().set_selection(workspace_id, list(sample_ids))

    def show_similar(
        self,
        sample_id: str,
        *,
        workspace_id: str = "default",
        layout_key: str | None = None,
        space_key: str | None = None,
        k: int = 18,
        source: str = "python",
    ) -> None:
        """Show nearest-neighbor results in the Samples panel."""

        self.set_samples_retrieval(
            sample_id,
            workspace_id=workspace_id,
            layout_key=layout_key,
            space_key=space_key,
            k=k,
            source=source,
        )

    def set_samples_retrieval(
        self,
        sample_id: str,
        *,
        workspace_id: str = "default",
        layout_key: str | None = None,
        space_key: str | None = None,
        k: int = 18,
        source: str = "python",
    ) -> None:
        """Set Samples panel retrieval state."""

        self._session.control.run(
            "samples.retrieval.set-anchor",
            target={"workspace_id": workspace_id},
            args={
                "sample_id": sample_id,
                "layout_key": layout_key,
                "space_key": space_key,
                "k": k,
                "source": source,
            },
        )

    def set_samples_retrieval_k(
        self,
        k: int,
        *,
        workspace_id: str = "default",
    ) -> None:
        """Update the active Samples retrieval result count."""

        self._session.control.run(
            "samples.retrieval.set-k",
            target={"workspace_id": workspace_id},
            args={"k": k},
        )

    def clear_samples_retrieval(self, *, workspace_id: str = "default") -> None:
        """Clear Samples panel retrieval state."""

        self._session.control.run(
            "samples.retrieval.clear",
            target={"workspace_id": workspace_id},
        )

    def query_by_text(
        self,
        query_text: str,
        *,
        workspace_id: str = "default",
        layout_key: str | None = None,
        space_key: str | None = None,
        k: int = 18,
        source: str = "python",
    ) -> list[tuple[Any, float]]:
        """Run a text query against the workspace dataset and show results in the Samples panel."""

        self._session.control.run(
            "samples.retrieval.set-text-query",
            target={"workspace_id": workspace_id},
            args={
                "query_text": query_text,
                "layout_key": layout_key,
                "space_key": space_key,
                "k": k,
                "source": source,
            },
        )
        dataset = self._runtime().get_dataset(workspace_id=workspace_id)
        return dataset.find_similar_by_text(
            query_text,
            k=k,
            space_key=space_key,
            layout_key=layout_key,
        )

    def add_extension(
        self,
        folder: str | os.PathLike[str],
        *,
        workspace_id: str = "default",
        add_panels: bool = False,
    ):
        """Register an extension folder with the current runtime.

        By default this registers extension tools and panel definitions without
        instantiating manifest panels. Concrete panel placement belongs in a
        workspace view, usually with ``hv.ui.ExtensionPanel(...)``.
        """

        return self._runtime().install_extension(
            workspace_id,
            Path(folder),
            add_panels=add_panels,
        )

    def list_panel_definitions(self) -> list[dict[str, Any]]:
        """Return built-in and installed extension panel definitions."""

        return [
            definition.to_dict()
            for definition in self._runtime().list_panel_definitions()
        ]


def launch(
    dataset: Dataset,
    port: int = 6262,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    notebook: bool | None = None,
    height: int = 800,
    reuse_server: bool = False,
    view: ui_module.View | None = None,
    block: bool = True,
    workspace_id: str = "default",
) -> Session:
    """Launch the HyperView visualization server.

    Note:
        HyperView needs at least one visualization to display. If no layouts
        exist yet but embedding spaces do, this function computes one default
        layout automatically.

    Args:
        dataset: The dataset to visualize.
        port: Port to run the server on.
        host: Host to bind to.
        open_browser: Whether to open a browser window.
        notebook: Whether to display in a notebook. If None, auto-detects.
        height: Height of the iframe in the notebook.
        reuse_server: If True, and the requested port is already serving HyperView,
            attach to the existing server instead of starting a new one. For safety,
            this will only attach when the existing server reports the same dataset
            name (via `/__hyperview__/health`).
        view: Optional UI view composition to apply before opening the app.
        block: If True in script mode, keep the server alive until interrupted.
            Set to False when the caller wants to manage the returned session.
        workspace_id: Workspace id to attach the dataset to.

    Returns:
        A Session object.

    Example:
        >>> import hyperview as hv
        >>> dataset = hv.Dataset("my_dataset")
        >>> dataset.add_images_dir("/path/to/images", label_from_folder=True)
        >>> dataset.compute_embeddings(model="openai/clip-vit-base-patch32")
        >>> dataset.compute_visualization()
        >>> hv.launch(dataset)
    """
    if notebook is None:
        # Colab is always a notebook environment, even if _is_notebook() fails to detect it
        notebook = _is_notebook() or _is_colab()

    if _is_colab() and host == "127.0.0.1":
        # Colab port forwarding/proxying is most reliable when the server binds
        # to all interfaces.
        host = "0.0.0.0"

    # Preflight: avoid doing expensive work if the port is already in use.
    # If it's already serving HyperView and reuse_server=True, we can safely attach.
    connect_host = "127.0.0.1" if host == "0.0.0.0" else host
    health_url = f"http://{connect_host}:{port}/__hyperview__/health"

    if _can_connect(connect_host, port, timeout_s=0.2):
        health = _try_read_health(health_url, timeout_s=0.2)
        if health is not None and health.name == "hyperview":
            if not reuse_server:
                raise RuntimeError(
                    "HyperView failed to start because the port is already serving "
                    f"HyperView (port={port}, dataset={health.dataset}, "
                    f"session_id={health.session_id}, pid={health.pid}). "
                    "Choose a different port, stop the existing server, or pass "
                    "reuse_server=True to attach."
                )

            if health.dataset is not None and health.dataset != dataset.name:
                raise RuntimeError(
                    "HyperView refused to attach to the existing server because it is "
                    f"serving a different dataset (port={port}, dataset={health.dataset}). "
                    f"Requested dataset={dataset.name}. Stop the existing server or "
                    "choose a different port."
                )

            if view is not None:
                raise RuntimeError(
                    "Cannot apply a launch view while reuse_server=True because the "
                    "existing server owns the runtime state. Use reuse_server=False "
                    "or apply the view through the control-plane API."
                )
            runtime = HyperViewRuntime()
            runtime.attach_dataset_instance(workspace_id, dataset, activate_workspace=True)
            session = Session(runtime, host, port, dataset, controls_runtime=False)
            if health.session_id is not None:
                session.session_id = health.session_id

            if notebook:
                if _is_colab():
                    print(
                        f"\nHyperView is already running (Colab, port={session.port}). "
                        "Use the link below to open it."
                    )
                else:
                    print(
                        f"\nHyperView is already running at {session.url} (port={session.port}). "
                        "Opening a new tab..."
                    )
                session.show(height=height)
            else:
                print(f"\nHyperView is already running at {session.url} (port={session.port}).")
                if open_browser:
                    session.open_browser()

            return session

        raise RuntimeError(
            "HyperView failed to start because the port is already in use "
            f"by a non-HyperView service (port={port}). Choose a different "
            "port or stop the process listening on that port."
        )

    layouts = dataset.list_layouts()
    spaces = dataset.list_spaces()

    if not layouts and not spaces:
        raise ValueError(
            "HyperView launch requires at least one visualization or embedding space. "
            "No visualizations or embedding spaces were found. "
            "Call `dataset.compute_embeddings()` and `dataset.compute_visualization()` "
            "or `dataset.set_coords()` before `hv.launch()`."
        )

    if not layouts:
        default_layout = _resolve_default_launch_layout(dataset)

        print(f"No visualizations found. Computing {default_layout} visualization...")
        # Let compute_visualization pick the most appropriate default space.
        dataset.compute_visualization(
            space_key=None,
            layout=default_layout,
        )

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance(workspace_id, dataset, activate_workspace=True)
    session = Session(runtime, host, port, dataset)
    if view is not None:
        session.ui.apply_view(view, workspace_id=workspace_id)

    if notebook:
        session.start(background=True)
        if _is_colab():
            print(
                f"\nHyperView is running (Colab, port={session.port}). "
                "Use the link below to open it."
            )
        else:
            print(f"\nHyperView is running at {session.url}. Opening a new tab...")
        session.show(height=height)
    else:
        session.start(background=True)
        print("   Press Ctrl+C to stop.\n")
        print(f"\nHyperView is running at {session.url}")

        if open_browser:
            session.open_browser()

        if block:
            session.wait()

    return session


def _is_notebook() -> bool:
    """Check if running in a notebook environment."""
    try:
        from IPython import get_ipython
    except ImportError:
        return False

    shell = get_ipython()
    return shell is not None and shell.__class__.__name__ == "ZMQInteractiveShell"


def _is_colab() -> bool:
    """Check if running inside a Google Colab notebook runtime."""
    if os.environ.get("COLAB_RELEASE_TAG"):
        return True
    if find_spec("google.colab") is not None:
        return True
    return False
