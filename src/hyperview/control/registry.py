"""Command registry and typed dispatch helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from hyperview.control.aliases import resolve_command_alias
from hyperview.control.models import CommandError, CommandMetadata, CommandOwner

if TYPE_CHECKING:
    from hyperview.runtime import HyperViewRuntime, WorkspaceState


class EmptyArgs(BaseModel):
    """Argument model for commands without arguments."""

    model_config = {"extra": "forbid"}


@dataclass(frozen=True)
class CommandExecution:
    """Internal successful command execution result."""

    workspace: WorkspaceState | None = None
    result: dict[str, object] | None = None
    revision: int | None = None


CommandHandler = Callable[
    ["HyperViewRuntime", BaseModel, BaseModel],
    CommandExecution,
]


@dataclass(frozen=True)
class CommandSpec:
    """Registered command definition."""

    id: str
    owner: CommandOwner
    summary: str
    target_model: type[BaseModel]
    args_model: type[BaseModel]
    handler: CommandHandler

    def metadata(self) -> CommandMetadata:
        return CommandMetadata(
            id=self.id,
            owner=self.owner,
            summary=self.summary,
            target_schema=self.target_model.model_json_schema(),
            args_schema=self.args_model.model_json_schema(),
        )


class CommandRegistry:
    """In-memory command registry."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandSpec] = {}

    def register(self, spec: CommandSpec) -> None:
        if spec.id in self._commands:
            raise ValueError(f"Command already registered: {spec.id}")
        self._commands[spec.id] = spec

    def get(self, command_id: str) -> CommandSpec:
        command_id = resolve_command_alias(command_id)
        try:
            return self._commands[command_id]
        except KeyError as exc:
            raise CommandError("unknown_command", f"Unknown command: {command_id}") from exc

    def list_metadata(self) -> list[CommandMetadata]:
        return [self._commands[key].metadata() for key in sorted(self._commands)]

    def validate_target_and_args(self, spec: CommandSpec, target: object, args: object) -> tuple[BaseModel, BaseModel]:
        try:
            return spec.target_model.model_validate(target), spec.args_model.model_validate(args)
        except ValidationError as exc:
            raise CommandError("validation_error", str(exc)) from exc
