"""Typed control command dispatch for HyperView."""

from hyperview.control.models import (
    CommandEnvelope,
    CommandError,
    CommandErrorPayload,
    CommandMetadata,
    CommandResult,
)
from hyperview.control.registry import CommandRegistry, CommandSpec
from hyperview.control.service import ControlService
from hyperview.control.ui_panel import create_default_command_registry

__all__ = [
    "CommandEnvelope",
    "CommandError",
    "CommandErrorPayload",
    "CommandMetadata",
    "CommandRegistry",
    "CommandResult",
    "CommandSpec",
    "ControlService",
    "create_default_command_registry",
]
