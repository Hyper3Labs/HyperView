"""HyperView tool registry.

Tools are Python callables user code (or agents) can register with the
runtime. They are invoked from panels via ``useTool`` or from the CLI via
``hyperview tools run``.

This module is intentionally small:

* ``@tool("namespace.name")`` decorates a callable.
* ``ToolRegistry`` stores ``uri -> ToolRecord`` in memory.
* ``RunContext`` is the only argument a tool receives. It carries the
  current workspace, dataset, params, a per-extension writable storage
  directory, and convenience helpers for building URLs.

No schema DSL, no packaging, no marketplace. A tool is a Python function.
"""

from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote


_PENDING_TOOLS: list["ToolRecord"] = []
_PENDING_LOCK = threading.Lock()


@dataclass
class ToolRecord:
    """A single registered tool."""

    uri: str
    func: Callable[..., Any]
    description: str | None = None
    source_file: Path | None = None
    extension: str | None = None
    # Derived from ``inspect.signature`` for CLI help / agent introspection.
    signature: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "description": self.description,
            "extension": self.extension,
            "signature": dict(self.signature),
        }


def _describe_signature(func: Callable[..., Any]) -> dict[str, Any]:
    """Derive a lightweight JSON-friendly description from a callable."""

    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return {"params": []}

    params: list[dict[str, Any]] = []
    for name, param in sig.parameters.items():
        if name == "ctx":
            continue
        entry: dict[str, Any] = {
            "name": name,
            "kind": param.kind.name,
            "required": param.default is inspect.Parameter.empty,
        }
        if param.annotation is not inspect.Parameter.empty:
            entry["annotation"] = _annotation_name(param.annotation)
        if param.default is not inspect.Parameter.empty:
            try:
                entry["default"] = param.default
            except Exception:
                entry["default"] = repr(param.default)
        params.append(entry)

    result: dict[str, Any] = {"params": params}
    if sig.return_annotation is not inspect.Parameter.empty:
        result["returns"] = _annotation_name(sig.return_annotation)
    return result


def _annotation_name(annotation: Any) -> str:
    if isinstance(annotation, type):
        return annotation.__name__
    return repr(annotation)


def tool(uri: str, *, description: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a callable as a HyperView tool.

    When the decorated module is imported by the extension loader, each
    decorated callable is collected into the pending queue and then drained
    into the runtime's :class:`ToolRegistry`.
    """

    if not uri or not isinstance(uri, str):
        raise ValueError("tool() requires a non-empty string URI")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        record = ToolRecord(
            uri=uri,
            func=func,
            description=description or inspect.getdoc(func),
            signature=_describe_signature(func),
        )
        source = inspect.getsourcefile(func)
        if source:
            record.source_file = Path(source).resolve()
        with _PENDING_LOCK:
            _PENDING_TOOLS.append(record)
        return func

    return decorator


def drain_pending_tools() -> list[ToolRecord]:
    """Return and clear tools collected since the last drain."""

    with _PENDING_LOCK:
        records = list(_PENDING_TOOLS)
        _PENDING_TOOLS.clear()
    return records


class ToolRegistry:
    """In-process registry of tools. One instance lives on the runtime."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolRecord] = {}
        self._lock = threading.RLock()

    def register(self, record: ToolRecord) -> None:
        with self._lock:
            self._tools[record.uri] = record

    def unregister(self, uri: str) -> ToolRecord | None:
        with self._lock:
            return self._tools.pop(uri, None)

    def unregister_by_extension(self, extension: str) -> list[str]:
        removed: list[str] = []
        with self._lock:
            for uri in list(self._tools):
                if self._tools[uri].extension == extension:
                    del self._tools[uri]
                    removed.append(uri)
        return removed

    def get(self, uri: str) -> ToolRecord | None:
        with self._lock:
            return self._tools.get(uri)

    def list(self) -> list[ToolRecord]:
        with self._lock:
            return [self._tools[key] for key in sorted(self._tools)]


@dataclass
class RunContext:
    """Argument passed to every tool invocation.

    The tool sees a live reference to the workspace and dataset — there is
    no serialized snapshot. Tools that want to submit long-running work
    should use :meth:`submit_job` and return the resulting job id so the
    calling panel can poll via the existing runtime SSE stream.
    """

    runtime: Any  # HyperViewRuntime; typed as Any to avoid import cycle
    workspace_id: str
    dataset: Any | None
    params: dict[str, Any]
    # Per-extension writable storage (under panel-content serving root so
    # panels can render images/files the tool wrote).
    extension_storage: Path
    extension_name: str

    @property
    def workspace(self) -> Any:
        return self.runtime.get_workspace(self.workspace_id)

    def url_for(self, path: Path | str) -> str:
        """Return a panel-content URL for a file under ``extension_storage``."""

        resolved = Path(path).resolve()
        try:
            rel = resolved.relative_to(self.extension_storage.resolve())
        except ValueError as exc:
            raise ValueError(
                f"Path {resolved} is not inside extension storage "
                f"{self.extension_storage}"
            ) from exc
        return (
            "/api/panels/content/"
            f"{quote(self.workspace_id, safe='')}/"
            f"{quote(self.extension_name, safe='')}/"
            + "/".join(quote(part, safe="") for part in rel.parts)
            + f"?v={self.runtime.version}"
        )

    def submit_job(
        self,
        *,
        kind: str,
        target: Callable[[], Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job = self.runtime.submit_job(
            kind=kind,
            workspace_id=self.workspace_id,
            dataset_name=self.dataset.name if self.dataset is not None else None,
            params=dict(params or {}),
            target=target,
        )
        return job.to_dict()
