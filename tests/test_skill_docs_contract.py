"""The installed HyperView skill must describe the CLI that actually ships.

Coding agents copy skill examples literally, so a command or flag that drifts
out of the parser becomes a repeated failure across every demo an agent writes.
These tests parse the shipped skill markdown and check each documented
invocation against the real argparse tree.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from hyperview.cli import _build_control_parser

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "hyperview-cli"

# A documented token that is a placeholder rather than a real argument.
_PLACEHOLDER_PREFIXES = ("-", "<", "$", "{")


def _subparser_actions(parser: argparse.ArgumentParser):
    return [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]


def _command_tree(parser: argparse.ArgumentParser) -> dict[tuple[str, ...], set[str]]:
    """Map every reachable subcommand path to the options it accepts."""

    tree: dict[tuple[str, ...], set[str]] = {}

    def walk(node: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        options = {
            option
            for action in node._actions
            for option in action.option_strings
            if option.startswith("--")
        }
        tree[path] = options
        for action in _subparser_actions(node):
            for name, child in action.choices.items():
                walk(child, path + (name,))

    walk(parser, ())
    return tree


def _documented_invocations() -> list[tuple[Path, str]]:
    invocations: list[tuple[Path, str]] = []
    for doc in sorted(SKILL_DIR.rglob("*.md")):
        # Join shell line continuations so multi-line examples parse as one command.
        text = re.sub(r"\\\s*\n\s*", " ", doc.read_text(encoding="utf-8"))
        for line in text.splitlines():
            line = line.strip().removeprefix("$ ").strip()
            if line.startswith("hyperview "):
                invocations.append((doc, line))
    return invocations


def _split(
    invocation: str, tree: dict[tuple[str, ...], set[str]]
) -> tuple[tuple[str, ...], set[str]]:
    """Resolve an example into its subcommand path and the long flags it uses.

    Only tokens that name a real subcommand extend the path; the first token
    that does not (a positional argument such as a dataset name) ends it.
    """

    tokens = invocation.split()[1:]
    path: tuple[str, ...] = ()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith(_PLACEHOLDER_PREFIXES):
            break
        if path + (token,) not in tree:
            break
        path += (token,)
        index += 1
    used = set(re.findall(r"(?<!\S)--[A-Za-z0-9][A-Za-z0-9-]*", " ".join(tokens[index:])))
    return path, used


def test_skill_documents_at_least_the_core_command_surface() -> None:
    invocations = _documented_invocations()

    assert len(invocations) >= 40, "skill reference lost most of its CLI examples"


def test_every_documented_command_path_exists() -> None:
    tree = _command_tree(_build_control_parser())

    unknown = sorted(
        {
            (invocation.split()[1], doc.name)
            for doc, invocation in _documented_invocations()
            for path, _ in [_split(invocation, tree)]
            if not path
        }
    )

    assert not unknown, f"skill documents commands the CLI does not expose: {unknown}"


def test_every_documented_flag_exists_on_its_command() -> None:
    tree = _command_tree(_build_control_parser())

    problems = []
    for doc, invocation in _documented_invocations():
        path, used = _split(invocation, tree)
        known = tree.get(path)
        if known is None:
            continue  # covered by the command-path test
        missing = sorted(used - known)
        if missing:
            problems.append((doc.name, " ".join(path), missing))

    assert not problems, f"skill documents flags the CLI does not accept: {problems}"
