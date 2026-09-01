"""Shipped Python examples must call the API that actually ships.

A demo calling `hv.launch(dataset, workspace=...)` when the parameter is named
`workspace_id` fails only when someone runs it, so the mistake survives review
and reaches every reader who copies the snippet. These tests resolve each
keyword argument in the examples and the skill's Python blocks against the real
signature, the same way `test_skill_docs_contract` does for the CLI.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import hyperview as hv

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples"
SKILL_DIR = ROOT / ".agents" / "skills" / "hyperview-cli"


def _python_sources() -> list[tuple[str, str]]:
    """Every runnable Python snippet we ship, as (label, source) pairs."""

    sources = [
        (str(path.relative_to(ROOT)), path.read_text(encoding="utf-8"))
        for path in sorted(EXAMPLES_DIR.rglob("*.py"))
    ]
    for doc in sorted(SKILL_DIR.rglob("*.md")):
        text = doc.read_text(encoding="utf-8")
        for index, block in enumerate(re.findall(r"```python\n(.*?)```", text, re.S)):
            sources.append((f"{doc.name}#python[{index}]", block))
    return sources


def _hv_calls(source: str):
    """Yield (lineno, attribute_name, call) for every `hv.<name>(...)` call."""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Prose snippets are allowed to elide code; only real programs are checked.
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "hv"
        ):
            yield node.lineno, func.attr, node


def test_examples_and_skill_snippets_reference_the_public_package() -> None:
    labels = {label for label, _ in _python_sources()}

    assert any(label.startswith("examples/") for label in labels), "examples/ went missing"


def test_every_hv_call_names_a_real_public_function() -> None:
    unknown = sorted(
        {
            (label, name)
            for label, source in _python_sources()
            for _, name, _ in _hv_calls(source)
            if not callable(getattr(hv, name, None))
        }
    )

    assert not unknown, f"snippets call functions hyperview does not export: {unknown}"


def test_every_hv_keyword_argument_exists_on_its_function() -> None:
    problems = []
    for label, source in _python_sources():
        for lineno, name, call in _hv_calls(source):
            func = getattr(hv, name, None)
            if not callable(func):
                continue  # covered by the export test
            try:
                signature = inspect.signature(func)
            except (TypeError, ValueError):
                continue
            if any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            ):
                continue
            missing = sorted(
                keyword.arg
                for keyword in call.keywords
                if keyword.arg and keyword.arg not in signature.parameters
            )
            if missing:
                problems.append((label, lineno, f"hv.{name}", missing))

    assert not problems, f"snippets pass keywords the API does not accept: {problems}"
