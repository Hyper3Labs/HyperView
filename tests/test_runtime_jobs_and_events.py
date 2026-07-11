from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

from hyperview.runtime import (
    HyperViewRuntime,
    JobRegistry,
    JobState,
    ProviderRegistry,
    WorkspaceRegistry,
)


def _runtime(tmp_path: Path) -> HyperViewRuntime:
    return HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
        job_registry=JobRegistry(tmp_path / "jobs.json"),
    )


def test_wait_for_version_wakes_immediately_on_version_bump(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    async def wait_for_bump() -> tuple[int | None, float]:
        previous = runtime.version
        waiter = asyncio.create_task(runtime.wait_for_version(previous, timeout=1.0))
        await asyncio.sleep(0)
        started = time.monotonic()
        runtime._bump_version()
        return await waiter, time.monotonic() - started

    version, elapsed = asyncio.run(wait_for_bump())

    assert version == 2
    assert elapsed < 0.2


def test_job_registry_round_trip_marks_active_jobs_interrupted(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    registry = JobRegistry(path)
    registry.update(
        JobState(
            id="running-job",
            kind="embeddings.compute",
            workspace_id="default",
            dataset_name="images",
            status="running",
            started_at=123,
            params={"model": "clip", "layouts": ["umap-2d"]},
        )
    )
    registry.update(
        JobState(
            id="completed-job",
            kind="layouts.compute",
            workspace_id="default",
            dataset_name="images",
            status="completed",
            started_at=100,
            finished_at=110,
            result={"layout_keys": ["clip__umap-2d"]},
            params={"space_key": "clip"},
        )
    )

    reloaded = JobRegistry(path)

    interrupted = reloaded.get("running-job")
    assert interrupted is not None
    assert interrupted.status == "interrupted"
    assert interrupted.finished_at is not None
    assert interrupted.error == "Job was interrupted when the previous runtime stopped."
    completed = reloaded.get("completed-job")
    assert completed is not None
    assert completed.to_dict() == registry.get("completed-job").to_dict()  # type: ignore[union-attr]


def test_submitted_jobs_execute_in_fifo_order(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    execution_order: list[str] = []

    def first_target() -> dict[str, str]:
        execution_order.append("first-start")
        first_started.set()
        assert release_first.wait(timeout=2.0)
        execution_order.append("first-end")
        return {"job": "first"}

    def second_target() -> dict[str, str]:
        execution_order.append("second")
        second_started.set()
        return {"job": "second"}

    first = runtime.submit_job(
        kind="test.first",
        workspace_id="default",
        dataset_name=None,
        params={},
        target=first_target,
    )
    assert first_started.wait(timeout=1.0)
    second = runtime.submit_job(
        kind="test.second",
        workspace_id="default",
        dataset_name=None,
        params={},
        target=second_target,
    )

    assert not second_started.wait(timeout=0.1)
    assert runtime.get_job(second.id).status == "queued"  # type: ignore[union-attr]
    release_first.set()
    assert second_started.wait(timeout=1.0)

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if runtime.get_job(second.id).status == "completed":  # type: ignore[union-attr]
            break
        time.sleep(0.01)

    assert runtime.get_job(first.id).status == "completed"  # type: ignore[union-attr]
    assert runtime.get_job(second.id).status == "completed"  # type: ignore[union-attr]
    assert execution_order == ["first-start", "first-end", "second"]


def test_queued_job_can_be_cancelled_before_execution(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    first_started = threading.Event()
    release_first = threading.Event()
    cancelled_target_ran = threading.Event()

    def blocking_target() -> dict[str, bool]:
        first_started.set()
        assert release_first.wait(timeout=2.0)
        return {"released": True}

    runtime.submit_job(
        kind="test.blocking",
        workspace_id="default",
        dataset_name=None,
        params={},
        target=blocking_target,
    )
    assert first_started.wait(timeout=1.0)
    queued = runtime.submit_job(
        kind="test.cancelled",
        workspace_id="default",
        dataset_name=None,
        params={},
        target=lambda: cancelled_target_ran.set(),
    )

    cancelled = runtime.cancel_job(queued.id)
    release_first.set()
    runtime._job_queue.join()

    assert cancelled.status == "cancelled"
    assert cancelled.cancellation_requested is True
    assert not cancelled_target_ran.is_set()
    assert JobRegistry(tmp_path / "jobs.json").get(queued.id).status == "cancelled"  # type: ignore[union-attr]


def test_jobs_cancel_control_command(tmp_path: Path) -> None:
    from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry

    runtime = _runtime(tmp_path)
    started = threading.Event()
    release = threading.Event()

    def blocking_target() -> dict[str, bool]:
        started.set()
        assert release.wait(timeout=2.0)
        return {"released": True}

    runtime.submit_job(
        kind="test.blocking",
        workspace_id="default",
        dataset_name=None,
        params={},
        target=blocking_target,
    )
    assert started.wait(timeout=1.0)
    queued = runtime.submit_job(
        kind="test.queued",
        workspace_id="default",
        dataset_name=None,
        params={},
        target=lambda: {"ran": True},
    )

    service = ControlService(runtime, create_default_command_registry())
    result = service.run(
        CommandEnvelope(
            command="jobs.cancel",
            target={"job_id": queued.id},
            args={},
        )
    )
    release.set()
    runtime._job_queue.join()

    assert result.ok
    assert result.result["job"]["id"] == queued.id
    assert result.result["job"]["status"] == "cancelled"

    missing = service.run(
        CommandEnvelope(command="jobs.cancel", target={"job_id": "nope"}, args={})
    )
    assert not missing.ok
    assert missing.error is not None
    assert missing.error.code == "not_found"
