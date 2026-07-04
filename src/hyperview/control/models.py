"""Models shared by HyperView control command surfaces."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CommandOwner = Literal["backend", "frontend"]
CommandErrorCode = Literal[
    "unknown_command",
    "validation_error",
    "not_found",
    "conflict",
    "requires_ui_client",
    "internal_error",
]


class CommandEnvelope(BaseModel):
    """Generic command request envelope."""

    model_config = ConfigDict(extra="forbid")

    command: str
    target: dict[str, Any] = Field(default_factory=dict)
    args: dict[str, Any] = Field(default_factory=dict)


class CommandMetadata(BaseModel):
    """Serializable command discovery metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str
    owner: CommandOwner
    summary: str
    target_schema: dict[str, Any] = Field(default_factory=dict)
    args_schema: dict[str, Any] = Field(default_factory=dict)


class CommandErrorPayload(BaseModel):
    """Machine-readable command error."""

    model_config = ConfigDict(extra="forbid")

    code: CommandErrorCode
    message: str


class CommandResult(BaseModel):
    """Generic command result envelope."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    command: str
    result: dict[str, Any] = Field(default_factory=dict)
    workspace: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    revision: int | None = None
    error: CommandErrorPayload | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class CommandError(Exception):
    """Expected command failure with a stable public code."""

    def __init__(self, code: CommandErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
