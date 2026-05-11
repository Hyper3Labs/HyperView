"""Install the HyperView agent skill into known agent skill directories.

This module bundles a small port of the install logic from
https://github.com/vercel-labs/skills (the de-facto skill installer for
Claude Skills-style agents). For every supported coding agent we know two
paths:

* ``config_dir`` -- the agent's user config directory. Its existence is the
  signal that the agent is installed on the current machine.
* ``global_skills_dir`` -- where the agent reads global skills from.

When invoked without ``--agent`` or ``--all-known``, the installer detects
which agents are installed (by checking ``config_dir``) and copies the
``hyperview-cli`` skill into each detected agent's ``global_skills_dir``,
plus the universal ``~/.agents/skills/`` fallback. Existing installs are
replaced by default so re-running ``hyperview skill install`` refreshes
old skill copies after a HyperView package upgrade.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

SKILL_NAME = "hyperview-cli"

UNIVERSAL_AGENT = "universal"


@dataclass(frozen=True)
class AgentProfile:
    """Where a coding agent looks for skills.

    All paths are written without ``~``; use ``Path.expanduser()`` when
    resolving. The skill name is appended at install time.
    """

    name: str
    display_name: str
    config_dir: str  # presence => agent is installed
    global_skills_dir: str  # ~user-scope skills root
    project_skills_dir: str  # project-scope skills root (relative)
    alternate_config_dirs: tuple[str, ...] = ()


def _xdg_config_home() -> str:
    """Return ``$XDG_CONFIG_HOME`` or its default (``~/.config``)."""
    return os.environ.get("XDG_CONFIG_HOME") or "~/.config"


def _build_agent_profiles() -> dict[str, AgentProfile]:
    xdg = _xdg_config_home()
    codex_home = os.environ.get("CODEX_HOME") or "~/.codex"
    claude_home = os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"
    profiles = [
        AgentProfile(
            name="claude-code",
            display_name="Claude Code",
            config_dir=claude_home,
            global_skills_dir=f"{claude_home}/skills",
            project_skills_dir=".claude/skills",
        ),
        AgentProfile(
            name="github-copilot",
            display_name="GitHub Copilot",
            config_dir="~/.copilot",
            global_skills_dir="~/.copilot/skills",
            project_skills_dir=".github/skills",
        ),
        AgentProfile(
            name="cursor",
            display_name="Cursor",
            config_dir="~/.cursor",
            global_skills_dir="~/.cursor/skills",
            project_skills_dir=".cursor/skills",
        ),
        AgentProfile(
            name="codex",
            display_name="Codex",
            config_dir=codex_home,
            global_skills_dir=f"{codex_home}/skills",
            project_skills_dir=".agents/skills",
            alternate_config_dirs=("/etc/codex",),
        ),
        AgentProfile(
            name="opencode",
            display_name="OpenCode",
            config_dir=f"{xdg}/opencode",
            global_skills_dir=f"{xdg}/opencode/skills",
            project_skills_dir=".agents/skills",
        ),
        AgentProfile(
            name="continue",
            display_name="Continue",
            config_dir="~/.continue",
            global_skills_dir="~/.continue/skills",
            project_skills_dir=".continue/skills",
        ),
        AgentProfile(
            name="windsurf",
            display_name="Windsurf",
            config_dir="~/.codeium/windsurf",
            global_skills_dir="~/.codeium/windsurf/skills",
            project_skills_dir=".windsurf/skills",
        ),
        AgentProfile(
            name="cline",
            display_name="Cline",
            config_dir="~/.cline",
            global_skills_dir="~/.agents/skills",
            project_skills_dir=".agents/skills",
        ),
        AgentProfile(
            name="roo",
            display_name="Roo Code",
            config_dir="~/.roo",
            global_skills_dir="~/.roo/skills",
            project_skills_dir=".roo/skills",
        ),
        AgentProfile(
            name="kilo",
            display_name="Kilo Code",
            config_dir="~/.kilocode",
            global_skills_dir="~/.kilocode/skills",
            project_skills_dir=".kilocode/skills",
        ),
        AgentProfile(
            name="kiro-cli",
            display_name="Kiro CLI",
            config_dir="~/.kiro",
            global_skills_dir="~/.kiro/skills",
            project_skills_dir=".kiro/skills",
        ),
        AgentProfile(
            name="gemini-cli",
            display_name="Gemini CLI",
            config_dir="~/.gemini",
            global_skills_dir="~/.gemini/skills",
            project_skills_dir=".agents/skills",
        ),
        AgentProfile(
            name="qwen-code",
            display_name="Qwen Code",
            config_dir="~/.qwen",
            global_skills_dir="~/.qwen/skills",
            project_skills_dir=".qwen/skills",
        ),
        AgentProfile(
            name="goose",
            display_name="Goose",
            config_dir=f"{xdg}/goose",
            global_skills_dir=f"{xdg}/goose/skills",
            project_skills_dir=".goose/skills",
        ),
        AgentProfile(
            name="aider-desk",
            display_name="AiderDesk",
            config_dir="~/.aider-desk",
            global_skills_dir="~/.aider-desk/skills",
            project_skills_dir=".aider-desk/skills",
        ),
        AgentProfile(
            name=UNIVERSAL_AGENT,
            display_name="Universal (.agents)",
            config_dir="~/.agents",  # always installed; treated as detected
            global_skills_dir="~/.agents/skills",
            project_skills_dir=".agents/skills",
        ),
    ]
    return {profile.name: profile for profile in profiles}


AGENT_PROFILES: dict[str, AgentProfile] = _build_agent_profiles()


@dataclass(frozen=True)
class SkillInstallResult:
    skill: str
    source: str
    destination: str
    scope: str
    agent: str
    action: str
    installed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "source": self.source,
            "destination": self.destination,
            "scope": self.scope,
            "agent": self.agent,
            "action": self.action,
            "installed": self.installed,
        }


def _repo_skill_source() -> Path | None:
    repo_root = Path(__file__).resolve().parents[2]
    source = repo_root / ".agents" / "skills" / SKILL_NAME
    if source.is_dir():
        return source
    return None


def _packaged_skill_source() -> resources.abc.Traversable:
    return resources.files("hyperview").joinpath("agent_assets", "skills", SKILL_NAME)


def _resolve_skill_source() -> Path | resources.abc.Traversable:
    repo_source = _repo_skill_source()
    if repo_source is not None:
        return repo_source
    package_source = _packaged_skill_source()
    if package_source.is_dir():
        return package_source
    raise FileNotFoundError(f"Packaged skill asset not found: {SKILL_NAME}")


def _expand(path: str) -> Path:
    return Path(path).expanduser()


def _agent_skills_root(profile: AgentProfile, scope: str) -> Path:
    if scope == "project":
        return Path.cwd() / profile.project_skills_dir
    if scope == "user":
        return _expand(profile.global_skills_dir)
    raise ValueError("Skill scope must be 'project' or 'user'.")


def detect_installed_agents() -> list[str]:
    """Return the names of agents whose config directory exists locally.

    The universal entry is always included so at least one install target
    is available even on a freshly bootstrapped machine.
    """
    detected: list[str] = []
    for name, profile in AGENT_PROFILES.items():
        config_paths = (profile.config_dir, *profile.alternate_config_dirs)
        if name == UNIVERSAL_AGENT or any(_expand(path).exists() for path in config_paths):
            detected.append(name)
    return detected


def resolve_skill_destination(
    *,
    scope: str = "user",
    agent: str = UNIVERSAL_AGENT,
    destination: str | None = None,
) -> Path:
    if destination is not None:
        return Path(destination).expanduser().resolve()
    profile = AGENT_PROFILES.get(agent)
    if profile is None:
        choices = ", ".join(sorted(AGENT_PROFILES))
        raise ValueError(f"Unknown agent '{agent}'. Choose one of: {choices}.")
    return (_agent_skills_root(profile, scope) / SKILL_NAME).resolve()


def _copy_skill_tree(source: Path | resources.abc.Traversable, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        child_destination = destination / child.name
        if child.is_dir():
            _copy_skill_tree(child, child_destination)
            continue
        child_destination.parent.mkdir(parents=True, exist_ok=True)
        child_destination.write_bytes(child.read_bytes())


def _replace_destination(destination: Path) -> None:
    if destination.is_dir():
        shutil.rmtree(destination)
    else:
        destination.unlink()


def _source_path(source: Path | resources.abc.Traversable) -> Path | None:
    if isinstance(source, Path):
        return source.resolve()
    return None


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _install_one(
    *,
    source: Path | resources.abc.Traversable,
    scope: str,
    agent: str,
    destination: str | None,
    force: bool,
    dry_run: bool,
) -> SkillInstallResult:
    resolved_destination = resolve_skill_destination(
        scope=scope,
        agent=agent,
        destination=destination,
    )
    exists = resolved_destination.exists()
    source_path = _source_path(source)
    destination_path = resolved_destination.resolve(strict=False)
    source_is_destination = source_path is not None and source_path == destination_path

    if source_path is not None and _paths_overlap(source_path, destination_path):
        if source_is_destination:
            action = "would-skip" if dry_run else "already-current"
            return SkillInstallResult(
                skill=SKILL_NAME,
                source=str(source),
                destination=str(resolved_destination),
                scope=scope,
                agent=agent,
                action=action,
                installed=not dry_run,
            )
        raise ValueError(
            "Refusing to install because source and destination overlap: "
            f"{source_path} -> {destination_path}"
        )

    if dry_run:
        action = "would-replace" if exists else "would-install"
        return SkillInstallResult(
            skill=SKILL_NAME,
            source=str(source),
            destination=str(resolved_destination),
            scope=scope,
            agent=agent,
            action=action,
            installed=False,
        )

    if exists and destination is not None and resolved_destination.name != SKILL_NAME and not force:
        raise ValueError(
            "Refusing to replace an existing custom destination that is not named "
            f"'{SKILL_NAME}'. Pass a final skill directory or use --yes to replace it."
        )

    if exists:
        _replace_destination(resolved_destination)

    _copy_skill_tree(source, resolved_destination)
    return SkillInstallResult(
        skill=SKILL_NAME,
        source=str(source),
        destination=str(resolved_destination),
        scope=scope,
        agent=agent,
        action="replaced" if exists else "installed",
        installed=True,
    )


def install_skill(
    *,
    scope: str = "user",
    agents: list[str] | None = None,
    all_known: bool = False,
    destination: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> SkillInstallResult | list[SkillInstallResult]:
    """Install the HyperView skill.

    With ``destination`` set, install to exactly that path and return a
    single ``SkillInstallResult``. Otherwise compute a list of agent
    targets (explicit ``agents``, or all known agents when ``all_known``,
    or the auto-detected set) and return a list of results, one per
    target.
    """
    if scope not in {"project", "user"}:
        raise ValueError("Skill scope must be 'project' or 'user'.")
    source = _resolve_skill_source()

    if destination is not None:
        return _install_one(
            source=source,
            scope=scope,
            agent=UNIVERSAL_AGENT,
            destination=destination,
            force=force,
            dry_run=dry_run,
        )

    if agents:
        unknown = [name for name in agents if name not in AGENT_PROFILES]
        if unknown:
            choices = ", ".join(sorted(AGENT_PROFILES))
            raise ValueError(
                f"Unknown agent(s): {', '.join(unknown)}. Choose from: {choices}."
            )
        targets = list(dict.fromkeys(agents))
    elif all_known:
        targets = list(AGENT_PROFILES)
    else:
        targets = detect_installed_agents()

    return [
        _install_one(
            source=source,
            scope=scope,
            agent=name,
            destination=None,
            force=force,
            dry_run=dry_run,
        )
        for name in targets
    ]
