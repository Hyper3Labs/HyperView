"""Command execution service."""

from __future__ import annotations

from pydantic import ValidationError

from hyperview.control.aliases import command_alias_deprecation_message
from hyperview.control.models import (
    CommandEnvelope,
    CommandError,
    CommandErrorCode,
    CommandErrorPayload,
    CommandResult,
)
from hyperview.control.registry import CommandRegistry
from hyperview.runtime import HyperViewRuntime


class ControlService:
    """Execute typed control commands against a runtime."""

    def __init__(self, runtime: HyperViewRuntime, registry: CommandRegistry) -> None:
        self.runtime = runtime
        self.registry = registry

    def list_commands(self) -> list[dict[str, object]]:
        return [metadata.model_dump() for metadata in self.registry.list_metadata()]

    def run(self, envelope: CommandEnvelope | dict[str, object]) -> CommandResult:
        request_command = (
            envelope.command
            if isinstance(envelope, CommandEnvelope)
            else str(envelope.get("command", ""))
        )
        warning = command_alias_deprecation_message(request_command)
        messages = [warning] if warning is not None else []
        try:
            request = (
                envelope
                if isinstance(envelope, CommandEnvelope)
                else CommandEnvelope.model_validate(envelope)
            )
            spec = self.registry.get(request.command)
            target, args = self.registry.validate_target_and_args(
                spec,
                request.target,
                request.args,
            )
            execution = spec.handler(self.runtime, target, args)
            messages.extend(execution.messages)
            workspace = execution.workspace.to_dict() if execution.workspace is not None else None
            snapshot = (
                self.runtime.snapshot(execution.workspace.id)
                if execution.workspace is not None
                else None
            )
            revision = execution.revision
            if revision is None and execution.workspace is not None:
                revision = execution.workspace.ui.view_revision
            return CommandResult(
                ok=True,
                command=spec.id,
                result=dict(execution.result or {}),
                workspace=workspace,
                snapshot=snapshot,
                revision=revision,
                messages=messages or None,
            )
        except ValidationError as exc:
            command = envelope.command if isinstance(envelope, CommandEnvelope) else ""
            return self._error_result(command, "validation_error", str(exc), messages)
        except CommandError as exc:
            command = envelope.command if isinstance(envelope, CommandEnvelope) else ""
            if not command and isinstance(envelope, dict):
                command_value = envelope.get("command")
                command = command_value if isinstance(command_value, str) else ""
            return self._error_result(command, exc.code, exc.message, messages)
        except KeyError as exc:
            command = envelope.command if isinstance(envelope, CommandEnvelope) else str(envelope.get("command", ""))
            message = str(exc.args[0]) if exc.args else str(exc)
            return self._error_result(command, "not_found", message, messages)
        except LookupError as exc:
            command = envelope.command if isinstance(envelope, CommandEnvelope) else str(envelope.get("command", ""))
            return self._error_result(command, "not_found", str(exc), messages)
        except ValueError as exc:
            command = envelope.command if isinstance(envelope, CommandEnvelope) else str(envelope.get("command", ""))
            return self._error_result(command, "validation_error", str(exc), messages)

    def _error_result(
        self,
        command: str,
        code: CommandErrorCode,
        message: str,
        messages: list[str] | None = None,
    ) -> CommandResult:
        return CommandResult(
            ok=False,
            command=command,
            messages=list(messages) if messages else None,
            error=CommandErrorPayload(code=code, message=message),
        )
