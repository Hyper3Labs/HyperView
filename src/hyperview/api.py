"""Public API for HyperView."""

import json
import socket
import threading
import time
import webbrowser
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import uvicorn

from hyperview.core.dataset import Dataset
from hyperview.server.app import create_app, set_dataset

__all__ = ["Dataset", "launch", "Session"]


@dataclass(frozen=True)
class _HealthResponse:
    name: str | None
    session_id: str | None


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
    )


class Session:
    """A session for the HyperView visualizer."""

    def __init__(self, dataset: Dataset, host: str, port: int):
        self.dataset = dataset
        self.host = host
        self.port = port
        # Prefer a browser-connectable host for user-facing URLs.
        # When binding to 0.0.0.0, users should connect via 127.0.0.1 locally.
        self.url = f"http://{self._connect_host}:{port}"
        self._server_thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._startup_error: BaseException | None = None
        self.session_id = uuid4().hex

    @property
    def _connect_host(self) -> str:
        return "127.0.0.1" if self.host == "0.0.0.0" else self.host

    @property
    def _health_url(self) -> str:
        return f"http://{self._connect_host}:{self.port}/__hyperview__/health"

    def _run_server(self):
        try:
            set_dataset(self.dataset)
            app = create_app(self.dataset, session_id=self.session_id)
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
            except (URLError, Exception) as exc:
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

    def show(self, height: int = 800):
        """Display the visualizer in a notebook."""
        try:
            from IPython.display import IFrame, display

            display(IFrame(self.url, width="100%", height=height))
        except ImportError:
            print(f"IPython not installed. Please visit {self.url} in your browser.")

    def open_browser(self):
        """Open the visualizer in a browser window."""
        webbrowser.open(self.url)


def launch(
    dataset: Dataset,
    port: int = 5151,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    notebook: bool | None = None,
    height: int = 800,
) -> Session:
    """Launch the HyperView visualization server.

    Args:
        dataset: The dataset to visualize.
        port: Port to run the server on.
        host: Host to bind to.
        open_browser: Whether to open a browser window.
        notebook: Whether to display in a notebook. If None, auto-detects.
        height: Height of the iframe in the notebook.

    Returns:
        A Session object.

    Example:
        >>> import hyperview as hv
        >>> dataset = hv.Dataset("my_dataset")
        >>> dataset.add_images_dir("/path/to/images", label_from_folder=True)
        >>> dataset.compute_embeddings()
        >>> dataset.compute_visualization()
        >>> hv.launch(dataset)
    """
    if notebook is None:
        notebook = _is_notebook()

    session = Session(dataset, host, port)

    if notebook:
        session.start(background=True)
        print(f"\nHyperView is running at {session.url}")
        session.show(height=height)
    else:
        session.start(background=True)
        print("   Press Ctrl+C to stop.\n")
        print(f"\nHyperView is running at {session.url}")

        if open_browser:
            session.open_browser()

        try:
            while True:
                # Keep the main thread alive so the daemon server thread can run.
                time.sleep(0.25)
                if session._server_thread is not None and not session._server_thread.is_alive():
                    raise RuntimeError("HyperView server stopped unexpectedly.")
        except KeyboardInterrupt:
            pass
        finally:
            session.stop()
            if session._server_thread is not None:
                session._server_thread.join(timeout=2.0)

    return session


def _is_notebook() -> bool:
    """Check if running in a notebook environment."""
    try:
        from IPython import get_ipython

        shell = get_ipython().__class__.__name__
        if shell == "ZMQInteractiveShell":
            return True  # Jupyter notebook or qtconsole
        elif shell == "TerminalInteractiveShell":
            return False  # Terminal running IPython
        else:
            return False  # Other type (?)
    except (ImportError, NameError):
        return False  # Probably standard Python interpreter
