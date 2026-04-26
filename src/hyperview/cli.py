"""Command-line interface for HyperView."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from hyperview import Dataset, launch
from hyperview.api import Session
from hyperview.core.dataset import parse_visualization_layout
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry


CONTROL_COMMANDS = {
    "serve",
    "status",
    "dataset",
    "provider",
    "workspace",
    "embeddings",
    "layouts",
    "jobs",
    "ui",
    "extension",
    "tools",
}


def _read_json_response(response: Any) -> Any:
    return json.loads(response.read().decode("utf-8"))


def _http_get_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=5.0) as response:
        return _read_json_response(response)


def _http_send_json(url: str, payload: dict[str, Any], method: str = "POST") -> Any:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=30.0) as response:
            return _read_json_response(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to reach HyperView server: {exc}") from exc


def _parse_scalar(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _parse_provider_args(values: list[str] | None) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(
                f"Provider args must use the form key=value, got '{value}'"
            )
        key, raw_value = value.split("=", 1)
        parsed[key] = _parse_scalar(raw_value)
    return parsed


def _server_base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _wait_for_job(base_url: str, job_id: str) -> dict[str, Any]:
    while True:
        payload = _http_get_json(f"{base_url}/api/jobs/{job_id}")
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.5)


def _print_output(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(payload)


def _build_legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hyperview",
        description="HyperView - Dataset visualization with hyperbolic embeddings",
    )

    parser.add_argument("--dataset", type=str, default=None)
    parser.add_argument("--dataset-json", type=str)
    parser.add_argument("--hf-dataset", type=str)
    parser.add_argument("--split", type=str, default=None)
    parser.add_argument("--hf-config", type=str, default=None)
    parser.add_argument("--image-key", type=str, default=None)
    parser.add_argument("--label-key", type=str, default=None)
    parser.add_argument("--label-names-key", type=str, default=None)
    parser.add_argument("--images-dir", type=str)
    parser.add_argument("--label-from-folder", action="store_true")
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--hf-streaming", action="store_true")
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hf-shuffle-buffer-size", type=int, default=1000)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--method", choices=["umap", "pca"], default="umap")
    parser.add_argument("--layout", action="append", dest="layouts", metavar="GEOMETRY[:2d|3d]")
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--min-dist", type=float, default=0.1)
    parser.add_argument("--metric", type=str, default="cosine")
    parser.add_argument("--force-layout", action="store_true")
    parser.add_argument("--port", type=int, default=6262)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--reuse-server", action="store_true")
    return parser


def _validate_legacy_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.layouts:
        canonical_layouts: list[str] = []
        seen_layouts: set[str] = set()
        for layout_spec in args.layouts:
            try:
                geometry, layout_dimension = parse_visualization_layout(layout_spec)
            except ValueError as exc:
                parser.error(str(exc))
            canonical_layout = f"{geometry}:{layout_dimension}d"
            if canonical_layout in seen_layouts:
                continue
            seen_layouts.add(canonical_layout)
            canonical_layouts.append(canonical_layout)
        args.layouts = canonical_layouts

    if args.hf_dataset and args.images_dir:
        parser.error("Use either --hf-dataset or --images-dir, not both.")
    if args.dataset_json and (args.hf_dataset or args.images_dir):
        parser.error("--dataset-json cannot be combined with --hf-dataset or --images-dir.")
    if args.dataset_json and args.dataset:
        parser.error("Use either --dataset or --dataset-json, not both.")
    if not args.dataset and not args.dataset_json:
        parser.error("Provide --dataset or --dataset-json.")
    if args.hf_dataset:
        if not args.split:
            parser.error("--split is required when using --hf-dataset.")
        if not args.image_key:
            parser.error("--image-key is required when using --hf-dataset.")
        if args.hf_shuffle_buffer_size < 1:
            parser.error("--hf-shuffle-buffer-size must be at least 1.")


def _print_ingestion_result(added: int, skipped: int) -> None:
    if skipped > 0:
        print(f"Loaded {added} samples ({skipped} already present)")
    else:
        print(f"Loaded {added} samples")


def _ingest_huggingface(dataset: Dataset, args: argparse.Namespace, dataset_name: str) -> None:
    added, skipped = dataset.add_from_huggingface(
        dataset_name,
        config=args.hf_config,
        split=args.split,
        image_key=args.image_key,
        label_key=args.label_key,
        label_names_key=args.label_names_key,
        max_samples=args.samples,
        shuffle=args.shuffle,
        seed=args.seed,
        streaming=args.hf_streaming,
        shuffle_buffer_size=args.hf_shuffle_buffer_size,
    )
    _print_ingestion_result(added, skipped)


def _prepare_dataset(args: argparse.Namespace) -> Dataset:
    if args.dataset_json:
        dataset = Dataset.load(args.dataset_json)
        print(f"Loaded {len(dataset)} samples")
        return dataset

    dataset = Dataset(args.dataset)
    print(f"Using dataset '{dataset.name}' ({len(dataset)} samples)")

    if args.hf_dataset:
        _ingest_huggingface(dataset, args, args.hf_dataset)
    elif args.images_dir:
        added, skipped = dataset.add_images_dir(
            args.images_dir,
            label_from_folder=args.label_from_folder,
        )
        _print_ingestion_result(added, skipped)

    return dataset


def _resolve_default_layouts(dataset: Dataset, space_key: str | None) -> list[str]:
    spaces = dataset.list_spaces()
    selected = next((space for space in spaces if space.space_key == space_key), None)
    if selected is not None:
        if selected.geometry == "hyperboloid":
            return ["poincare:2d"]
        if selected.geometry == "hypersphere":
            return ["spherical:3d"]
        return ["euclidean:2d"]
    if any(space.geometry not in ("hyperboloid", "hypersphere") for space in spaces):
        return ["euclidean:2d"]
    if any(space.geometry == "hypersphere" for space in spaces):
        return ["spherical:3d"]
    return ["poincare:2d"]


def _compute_layouts(dataset: Dataset, args: argparse.Namespace, space_key: str | None) -> None:
    target_layouts = args.layouts or _resolve_default_layouts(dataset, space_key)
    for target_layout in target_layouts:
        dataset.compute_visualization(
            space_key=space_key,
            method=args.method,
            layout=target_layout,
            n_neighbors=args.n_neighbors,
            min_dist=args.min_dist,
            metric=args.metric,
            force=args.force_layout,
        )


def _prepare_embeddings_and_layouts(dataset: Dataset, args: argparse.Namespace) -> None:
    has_spaces = len(dataset.list_spaces()) > 0
    if args.model is not None:
        space_key = dataset.compute_embeddings(model=args.model, show_progress=True)
        _compute_layouts(dataset, args, space_key)
        return
    if args.force_layout:
        if not has_spaces:
            raise ValueError("No embedding spaces found. Provide --model first.")
        _compute_layouts(dataset, args, space_key=None)
        return
    if not has_spaces:
        raise ValueError("No embedding spaces found. Provide --model first.")


def _run_legacy_cli(argv: list[str] | None = None) -> None:
    parser = _build_legacy_parser()
    args = parser.parse_args(argv)
    _validate_legacy_args(parser, args)
    dataset = _prepare_dataset(args)
    _prepare_embeddings_and_layouts(dataset, args)
    launch(
        dataset,
        port=args.port,
        host=args.host,
        open_browser=not args.no_browser,
        reuse_server=args.reuse_server,
    )


def _add_server_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6262)


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


def _add_dataset_source_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--hf-dataset")
    parser.add_argument("--split", default=None)
    parser.add_argument("--hf-config", default=None)
    parser.add_argument("--image-key", default=None)
    parser.add_argument("--label-key", default=None)
    parser.add_argument("--label-names-key", default=None)
    parser.add_argument("--images-dir")
    parser.add_argument("--label-from-folder", action="store_true")
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--hf-streaming", action="store_true")
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hf-shuffle-buffer-size", type=int, default=1000)


def _validate_dataset_source_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.hf_dataset and args.images_dir:
        parser.error("Use either --hf-dataset or --images-dir, not both.")
    if args.hf_dataset:
        if not args.split:
            parser.error("--split is required when using --hf-dataset.")
        if not args.image_key:
            parser.error("--image-key is required when using --hf-dataset.")
        if args.hf_shuffle_buffer_size < 1:
            parser.error("--hf-shuffle-buffer-size must be at least 1.")


def _dataset_payload(dataset: Dataset) -> dict[str, Any]:
    return {
        "name": dataset.name,
        "num_samples": len(dataset),
        "spaces": [
            {
                "space_key": space.space_key,
                "model_id": space.model_id,
                "dim": space.dim,
                "provider": space.provider,
                "geometry": space.geometry,
            }
            for space in dataset.list_spaces()
        ],
        "layouts": [
            {
                "layout_key": layout.layout_key,
                "space_key": layout.space_key,
                "method": layout.method,
                "geometry": layout.geometry,
            }
            for layout in dataset.list_layouts()
        ],
    }


def _build_control_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hyperview", description="HyperView runtime control CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--workspace", default=None)
    serve_parser.add_argument("--dataset", default=None)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=6262)
    serve_parser.add_argument("--no-browser", action="store_true")

    status_parser = subparsers.add_parser("status")
    _add_server_flags(status_parser)
    _add_json_flag(status_parser)

    dataset_parser = subparsers.add_parser("dataset")
    dataset_subparsers = dataset_parser.add_subparsers(dest="dataset_command", required=True)
    dataset_create = dataset_subparsers.add_parser("create")
    dataset_create.add_argument("dataset_name")
    _add_dataset_source_flags(dataset_create)
    _add_json_flag(dataset_create)
    dataset_list = dataset_subparsers.add_parser("list")
    _add_json_flag(dataset_list)
    dataset_inspect = dataset_subparsers.add_parser("inspect")
    dataset_inspect.add_argument("dataset_name")
    _add_json_flag(dataset_inspect)

    provider_parser = subparsers.add_parser("provider")
    provider_subparsers = provider_parser.add_subparsers(dest="provider_command", required=True)
    provider_register = provider_subparsers.add_parser("register")
    provider_register.add_argument("alias")
    provider_register.add_argument("--import-path", required=True)
    provider_register.add_argument("--description")
    provider_register.add_argument("--default", action="append", dest="defaults")
    provider_register.add_argument("--overwrite", action="store_true")
    _add_json_flag(provider_register)
    provider_list = provider_subparsers.add_parser("list")
    _add_json_flag(provider_list)
    provider_inspect = provider_subparsers.add_parser("inspect")
    provider_inspect.add_argument("alias")
    _add_json_flag(provider_inspect)
    provider_unregister = provider_subparsers.add_parser("unregister")
    provider_unregister.add_argument("alias")
    _add_json_flag(provider_unregister)

    workspace_parser = subparsers.add_parser("workspace")
    workspace_subparsers = workspace_parser.add_subparsers(dest="workspace_command", required=True)
    workspace_create = workspace_subparsers.add_parser("create")
    workspace_create.add_argument("workspace_id")
    workspace_create.add_argument("--dataset")
    workspace_create.add_argument("--activate", action="store_true")
    _add_json_flag(workspace_create)
    workspace_list = workspace_subparsers.add_parser("list")
    _add_json_flag(workspace_list)
    workspace_inspect = workspace_subparsers.add_parser("inspect")
    workspace_inspect.add_argument("workspace_id")
    _add_json_flag(workspace_inspect)
    workspace_set_dataset = workspace_subparsers.add_parser("set-dataset")
    workspace_set_dataset.add_argument("workspace_id")
    workspace_set_dataset.add_argument("dataset_name")
    _add_json_flag(workspace_set_dataset)
    workspace_set_active = workspace_subparsers.add_parser("set-active")
    workspace_set_active.add_argument("workspace_id")
    _add_json_flag(workspace_set_active)
    workspace_delete = workspace_subparsers.add_parser("delete")
    workspace_delete.add_argument("workspace_id")
    _add_json_flag(workspace_delete)

    embeddings_parser = subparsers.add_parser("embeddings")
    embeddings_subparsers = embeddings_parser.add_subparsers(dest="embeddings_command", required=True)
    embeddings_compute = embeddings_subparsers.add_parser("compute")
    _add_server_flags(embeddings_compute)
    embeddings_compute.add_argument("--workspace", required=True)
    embeddings_compute.add_argument("--dataset", required=True)
    embeddings_compute.add_argument("--model-id", required=True)
    embeddings_compute.add_argument("--provider")
    embeddings_compute.add_argument("--checkpoint")
    embeddings_compute.add_argument("--provider-arg", action="append", dest="provider_args")
    embeddings_compute.add_argument("--layout", action="append", dest="layouts")
    embeddings_compute.add_argument("--method", default="umap")
    embeddings_compute.add_argument("--n-neighbors", type=int, default=15)
    embeddings_compute.add_argument("--min-dist", type=float, default=0.1)
    embeddings_compute.add_argument("--metric", default="cosine")
    embeddings_compute.add_argument("--no-wait", action="store_true")
    _add_json_flag(embeddings_compute)

    layouts_parser = subparsers.add_parser("layouts")
    layouts_subparsers = layouts_parser.add_subparsers(dest="layouts_command", required=True)
    layouts_compute = layouts_subparsers.add_parser("compute")
    _add_server_flags(layouts_compute)
    layouts_compute.add_argument("--workspace", required=True)
    layouts_compute.add_argument("--dataset", required=True)
    layouts_compute.add_argument("--space-key")
    layouts_compute.add_argument("--layout", action="append", dest="layouts", required=True)
    layouts_compute.add_argument("--method", default="umap")
    layouts_compute.add_argument("--n-neighbors", type=int, default=15)
    layouts_compute.add_argument("--min-dist", type=float, default=0.1)
    layouts_compute.add_argument("--metric", default="cosine")
    layouts_compute.add_argument("--no-wait", action="store_true")
    _add_json_flag(layouts_compute)

    jobs_parser = subparsers.add_parser("jobs")
    jobs_subparsers = jobs_parser.add_subparsers(dest="jobs_command", required=True)
    jobs_list = jobs_subparsers.add_parser("list")
    _add_server_flags(jobs_list)
    _add_json_flag(jobs_list)
    jobs_inspect = jobs_subparsers.add_parser("inspect")
    _add_server_flags(jobs_inspect)
    jobs_inspect.add_argument("job_id")
    _add_json_flag(jobs_inspect)

    ui_parser = subparsers.add_parser("ui")
    ui_subparsers = ui_parser.add_subparsers(dest="ui_command", required=True)
    ui_workspace = ui_subparsers.add_parser("workspace")
    ui_workspace_subparsers = ui_workspace.add_subparsers(dest="ui_workspace_command", required=True)
    ui_workspace_set = ui_workspace_subparsers.add_parser("set")
    _add_server_flags(ui_workspace_set)
    ui_workspace_set.add_argument("workspace_id")
    _add_json_flag(ui_workspace_set)

    ui_layout = ui_subparsers.add_parser("layout")
    ui_layout_subparsers = ui_layout.add_subparsers(dest="ui_layout_command", required=True)
    ui_layout_set = ui_layout_subparsers.add_parser("set")
    _add_server_flags(ui_layout_set)
    ui_layout_set.add_argument("--workspace", required=True)
    ui_layout_set.add_argument("--layout-key", required=True)
    _add_json_flag(ui_layout_set)

    ui_selection = ui_subparsers.add_parser("selection")
    ui_selection_subparsers = ui_selection.add_subparsers(dest="ui_selection_command", required=True)
    ui_selection_set = ui_selection_subparsers.add_parser("set")
    _add_server_flags(ui_selection_set)
    ui_selection_set.add_argument("--workspace", required=True)
    ui_selection_set.add_argument("--ids", required=True)
    _add_json_flag(ui_selection_set)
    ui_selection_clear = ui_selection_subparsers.add_parser("clear")
    _add_server_flags(ui_selection_clear)
    ui_selection_clear.add_argument("--workspace", required=True)
    _add_json_flag(ui_selection_clear)

    ui_panel = ui_subparsers.add_parser("panel")
    ui_panel_subparsers = ui_panel.add_subparsers(dest="ui_panel_command", required=True)
    ui_panel_add = ui_panel_subparsers.add_parser("add")
    _add_server_flags(ui_panel_add)
    ui_panel_add.add_argument("--workspace", required=True)
    ui_panel_add.add_argument("--panel-id", required=True)
    ui_panel_add.add_argument("--title", required=True)
    ui_panel_add.add_argument("--module-file", required=True)
    ui_panel_add.add_argument("--position", choices=["center", "right", "bottom"], default="right")
    _add_json_flag(ui_panel_add)

    ui_panel_remove = ui_panel_subparsers.add_parser("remove")
    _add_server_flags(ui_panel_remove)
    ui_panel_remove.add_argument("--workspace", required=True)
    ui_panel_remove.add_argument("--panel-id", required=True)
    _add_json_flag(ui_panel_remove)

    extension_parser = subparsers.add_parser("extension")
    extension_subparsers = extension_parser.add_subparsers(dest="extension_command", required=True)

    extension_add = extension_subparsers.add_parser("add")
    _add_server_flags(extension_add)
    extension_add.add_argument("folder")
    extension_add.add_argument("--workspace", default=None)
    _add_json_flag(extension_add)

    extension_list = extension_subparsers.add_parser("list")
    _add_server_flags(extension_list)
    _add_json_flag(extension_list)

    extension_remove = extension_subparsers.add_parser("remove")
    _add_server_flags(extension_remove)
    extension_remove.add_argument("name")
    _add_json_flag(extension_remove)

    extension_reload = extension_subparsers.add_parser("reload")
    _add_server_flags(extension_reload)
    extension_reload.add_argument("name")
    _add_json_flag(extension_reload)

    tools_parser = subparsers.add_parser("tools")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command", required=True)

    tools_list = tools_subparsers.add_parser("list")
    _add_server_flags(tools_list)
    _add_json_flag(tools_list)

    tools_run = tools_subparsers.add_parser("run")
    _add_server_flags(tools_run)
    tools_run.add_argument("tool")
    tools_run.add_argument("--workspace", required=True)
    tools_run.add_argument("--param", action="append", dest="params", default=[])
    _add_json_flag(tools_run)

    return parser


def _run_server_command(args: argparse.Namespace) -> None:
    runtime = HyperViewRuntime()
    workspace_id = args.workspace or runtime.workspace_registry.active_workspace_id or "default"
    runtime.workspace_registry.ensure_workspace(workspace_id, activate=True)

    dataset_obj = None
    if args.dataset:
        runtime.set_workspace_dataset(workspace_id, args.dataset)
        dataset_obj = runtime.get_dataset(workspace_id, args.dataset)
    else:
        workspace = runtime.get_workspace(workspace_id)
        if workspace.dataset_name:
            dataset_obj = runtime.get_dataset(workspace_id, workspace.dataset_name)

    # Auto-discover extensions from .hyperview/extensions/ in the cwd.
    from hyperview.extensions import discover_local_extensions
    for folder in discover_local_extensions():
        try:
            installation = runtime.install_extension(workspace_id, folder)
            print(f"Loaded extension '{installation.manifest.name}' from {folder}")
        except Exception as exc:
            print(f"Failed to load extension at {folder}: {exc}")

    session = Session(runtime, args.host, args.port, dataset_obj)
    session.start(background=True)
    print(f"HyperView runtime is running at {session.url}")
    if not args.no_browser:
        session.open_browser()
    try:
        while True:
            time.sleep(0.25)
            if session._server_thread is not None and not session._server_thread.is_alive():
                raise RuntimeError("HyperView server stopped unexpectedly.")
    except KeyboardInterrupt:
        pass
    finally:
        session.stop()
        if session._server_thread is not None:
            session._server_thread.join(timeout=2.0)


def _run_status_command(args: argparse.Namespace) -> None:
    payload = _http_get_json(f"{_server_base_url(args.host, args.port)}/__hyperview__/health")
    _print_output(payload, as_json=args.json)


def _run_dataset_command(args: argparse.Namespace) -> None:
    if args.dataset_command == "list":
        runtime = HyperViewRuntime()
        _print_output({"datasets": runtime.list_available_datasets()}, as_json=args.json)
        return
    if args.dataset_command == "inspect":
        dataset = Dataset(args.dataset_name)
        _print_output({"dataset": _dataset_payload(dataset)}, as_json=args.json)
        return
    if args.dataset_command == "create":
        dataset_parser = argparse.ArgumentParser(add_help=False)
        _validate_dataset_source_args(dataset_parser, args)
        dataset = Dataset(args.dataset_name)
        if args.hf_dataset:
            added, skipped = dataset.add_from_huggingface(
                args.hf_dataset,
                config=args.hf_config,
                split=args.split,
                image_key=args.image_key,
                label_key=args.label_key,
                label_names_key=args.label_names_key,
                max_samples=args.samples,
                shuffle=args.shuffle,
                seed=args.seed,
                streaming=args.hf_streaming,
                shuffle_buffer_size=args.hf_shuffle_buffer_size,
                show_progress=not args.json,
            )
            if not args.json:
                _print_ingestion_result(added, skipped)
        elif args.images_dir:
            added, skipped = dataset.add_images_dir(
                args.images_dir,
                label_from_folder=args.label_from_folder,
            )
            if not args.json:
                _print_ingestion_result(added, skipped)
        _print_output({"dataset": _dataset_payload(dataset)}, as_json=args.json)
        return
    raise RuntimeError(f"Unsupported dataset command: {args.dataset_command}")


def _run_provider_command(args: argparse.Namespace) -> None:
    registry = ProviderRegistry()
    if args.provider_command == "register":
        payload = registry.register_python(
            args.alias,
            args.import_path,
            description=args.description,
            defaults=_parse_provider_args(args.defaults),
            overwrite=args.overwrite,
        ).to_dict()
        _print_output({"provider": payload}, as_json=args.json)
        return
    if args.provider_command == "list":
        _print_output({"providers": [provider.to_dict() for provider in registry.list()]}, as_json=args.json)
        return
    if args.provider_command == "inspect":
        registration = registry.get(args.alias)
        if registration is None:
            raise RuntimeError(f"Unknown provider alias: {args.alias}")
        payload = registration.to_dict()
        payload["available"] = registry.is_available(args.alias)
        _print_output({"provider": payload}, as_json=args.json)
        return
    if args.provider_command == "unregister":
        removed = registry.unregister(args.alias)
        _print_output({"removed": removed, "alias": args.alias}, as_json=args.json)
        return
    raise RuntimeError(f"Unsupported provider command: {args.provider_command}")


def _run_workspace_command(args: argparse.Namespace) -> None:
    registry = WorkspaceRegistry()
    if args.workspace_command == "create":
        workspace = registry.create_workspace(args.workspace_id, activate=args.activate)
        if args.dataset:
            workspace = registry.set_dataset(args.workspace_id, args.dataset)
        _print_output({"workspace": workspace.to_dict()}, as_json=args.json)
        return
    if args.workspace_command == "list":
        payload = {
            "active_workspace_id": registry.active_workspace_id,
            "workspaces": [workspace.to_dict() for workspace in registry.list()],
        }
        _print_output(payload, as_json=args.json)
        return
    if args.workspace_command == "inspect":
        workspace = registry.get(args.workspace_id)
        if workspace is None:
            raise RuntimeError(f"Unknown workspace: {args.workspace_id}")
        _print_output({"workspace": workspace.to_dict()}, as_json=args.json)
        return
    if args.workspace_command == "set-dataset":
        workspace = registry.set_dataset(args.workspace_id, args.dataset_name)
        _print_output({"workspace": workspace.to_dict()}, as_json=args.json)
        return
    if args.workspace_command == "set-active":
        workspace = registry.set_active_workspace(args.workspace_id)
        _print_output({"workspace": workspace.to_dict()}, as_json=args.json)
        return
    if args.workspace_command == "delete":
        active_workspace = registry.delete_workspace(args.workspace_id)
        payload = {
            "deleted_workspace_id": args.workspace_id,
            "active_workspace_id": registry.active_workspace_id,
            "workspaces": [workspace.to_dict() for workspace in registry.list()],
        }
        if active_workspace is not None:
            payload["workspace"] = active_workspace.to_dict()
        _print_output(payload, as_json=args.json)
        return
    raise RuntimeError(f"Unsupported workspace command: {args.workspace_command}")


def _run_embeddings_command(args: argparse.Namespace) -> None:
    base_url = _server_base_url(args.host, args.port)
    payload = _http_send_json(
        f"{base_url}/api/control/embeddings/compute",
        {
            "workspace_id": args.workspace,
            "dataset_name": args.dataset,
            "model": args.model_id,
            "provider": args.provider,
            "checkpoint": args.checkpoint,
            "provider_kwargs": _parse_provider_args(args.provider_args),
            "layouts": args.layouts,
            "method": args.method,
            "n_neighbors": args.n_neighbors,
            "min_dist": args.min_dist,
            "metric": args.metric,
        },
    )
    if args.no_wait:
        _print_output(payload, as_json=args.json)
        return
    _print_output({"job": _wait_for_job(base_url, payload["job"]["id"])}, as_json=args.json)


def _run_layouts_command(args: argparse.Namespace) -> None:
    base_url = _server_base_url(args.host, args.port)
    payload = _http_send_json(
        f"{base_url}/api/control/layouts/compute",
        {
            "workspace_id": args.workspace,
            "dataset_name": args.dataset,
            "space_key": args.space_key,
            "layouts": args.layouts,
            "method": args.method,
            "n_neighbors": args.n_neighbors,
            "min_dist": args.min_dist,
            "metric": args.metric,
        },
    )
    if args.no_wait:
        _print_output(payload, as_json=args.json)
        return
    _print_output({"job": _wait_for_job(base_url, payload["job"]["id"])}, as_json=args.json)


def _run_jobs_command(args: argparse.Namespace) -> None:
    base_url = _server_base_url(args.host, args.port)
    if args.jobs_command == "list":
        _print_output(_http_get_json(f"{base_url}/api/jobs"), as_json=args.json)
        return
    if args.jobs_command == "inspect":
        _print_output(_http_get_json(f"{base_url}/api/jobs/{args.job_id}"), as_json=args.json)
        return
    raise RuntimeError(f"Unsupported jobs command: {args.jobs_command}")


def _run_ui_command(args: argparse.Namespace) -> None:
    base_url = _server_base_url(args.host, args.port)
    if args.ui_command == "workspace" and args.ui_workspace_command == "set":
        payload = _http_send_json(
            f"{base_url}/api/control/workspaces/set-active",
            {"workspace_id": args.workspace_id},
        )
        _print_output(payload, as_json=args.json)
        return
    if args.ui_command == "layout" and args.ui_layout_command == "set":
        payload = _http_send_json(
            f"{base_url}/api/control/ui/layout",
            {"workspace_id": args.workspace, "layout_key": args.layout_key},
        )
        _print_output(payload, as_json=args.json)
        return
    if args.ui_command == "selection" and args.ui_selection_command == "set":
        sample_ids = [value for value in args.ids.split(",") if value]
        payload = _http_send_json(
            f"{base_url}/api/control/ui/selection",
            {"workspace_id": args.workspace, "sample_ids": sample_ids},
        )
        _print_output(payload, as_json=args.json)
        return
    if args.ui_command == "selection" and args.ui_selection_command == "clear":
        payload = _http_send_json(
            f"{base_url}/api/control/ui/selection",
            {"workspace_id": args.workspace, "sample_ids": []},
        )
        _print_output(payload, as_json=args.json)
        return
    if args.ui_command == "panel" and args.ui_panel_command == "add":
        module_file = str(Path(args.module_file).expanduser().resolve())
        payload = _http_send_json(
            f"{base_url}/api/control/ui/panels",
            {
                "workspace_id": args.workspace,
                "panel_id": args.panel_id,
                "title": args.title,
                "module_file": module_file,
                "position": args.position,
            },
        )
        _print_output(payload, as_json=args.json)
        return
    if args.ui_command == "panel" and args.ui_panel_command == "remove":
        payload = _http_send_json(
            f"{base_url}/api/control/ui/panels",
            {"workspace_id": args.workspace, "panel_id": args.panel_id},
            method="DELETE",
        )
        _print_output(payload, as_json=args.json)
        return
    raise RuntimeError("Unsupported ui command")


def _active_workspace_id(base_url: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    payload = _http_get_json(f"{base_url}/__hyperview__/health")
    resolved = payload.get("workspace_id")
    if not resolved:
        raise RuntimeError("No active workspace; pass --workspace")
    return str(resolved)


def _run_extension_command(args: argparse.Namespace) -> None:
    base_url = _server_base_url(args.host, args.port)
    if args.extension_command == "add":
        folder = str(Path(args.folder).expanduser().resolve())
        workspace_id = _active_workspace_id(base_url, args.workspace)
        payload = _http_send_json(
            f"{base_url}/api/control/extensions/install",
            {"workspace_id": workspace_id, "folder": folder},
        )
        _print_output(payload, as_json=args.json)
        return
    if args.extension_command == "list":
        _print_output(_http_get_json(f"{base_url}/api/extensions"), as_json=args.json)
        return
    if args.extension_command == "remove":
        payload = _http_send_json(
            f"{base_url}/api/control/extensions/remove",
            {"name": args.name},
            method="DELETE",
        )
        _print_output(payload, as_json=args.json)
        return
    if args.extension_command == "reload":
        workspace_id = _active_workspace_id(base_url, None)
        # Reload = re-install from its current folder
        ext_list = _http_get_json(f"{base_url}/api/extensions").get("extensions") or []
        match = next((item for item in ext_list if item.get("name") == args.name), None)
        if match is None:
            raise RuntimeError(f"Unknown extension: {args.name}")
        payload = _http_send_json(
            f"{base_url}/api/control/extensions/install",
            {"workspace_id": match.get("workspace_id") or workspace_id, "folder": match["folder"]},
        )
        _print_output(payload, as_json=args.json)
        return
    raise RuntimeError(f"Unsupported extension command: {args.extension_command}")


def _run_tools_command(args: argparse.Namespace) -> None:
    base_url = _server_base_url(args.host, args.port)
    if args.tools_command == "list":
        _print_output(_http_get_json(f"{base_url}/api/tools"), as_json=args.json)
        return
    if args.tools_command == "run":
        params: dict[str, Any] = {}
        for entry in args.params or []:
            if "=" not in entry:
                raise ValueError(f"--param must be key=value, got '{entry}'")
            key, raw = entry.split("=", 1)
            params[key] = _parse_scalar(raw)
        payload = _http_send_json(
            f"{base_url}/api/tools/run",
            {"tool": args.tool, "workspace_id": args.workspace, "params": params},
        )
        _print_output(payload, as_json=args.json)
        return
    raise RuntimeError(f"Unsupported tools command: {args.tools_command}")


def main(argv: list[str] | None = None):
    args_list = list(argv if argv is not None else sys.argv[1:])
    if not args_list or args_list[0] not in CONTROL_COMMANDS:
        _run_legacy_cli(args_list or None)
        return

    parser = _build_control_parser()
    args = parser.parse_args(args_list)
    if args.command == "serve":
        _run_server_command(args)
        return
    if args.command == "status":
        _run_status_command(args)
        return
    if args.command == "dataset":
        _run_dataset_command(args)
        return
    if args.command == "provider":
        _run_provider_command(args)
        return
    if args.command == "workspace":
        _run_workspace_command(args)
        return
    if args.command == "embeddings":
        _run_embeddings_command(args)
        return
    if args.command == "layouts":
        _run_layouts_command(args)
        return
    if args.command == "jobs":
        _run_jobs_command(args)
        return
    if args.command == "ui":
        _run_ui_command(args)
        return
    if args.command == "extension":
        _run_extension_command(args)
        return
    if args.command == "tools":
        _run_tools_command(args)
        return
    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
