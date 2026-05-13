"""
Build a one-hop dependency cluster for a Claude Code skill.

Given a skill (e.g., "prd" or "session-search"), find every other
artifact that references it, so an export audit can show the user the
full bundle that would ship together:

  - rules     ~/.claude/rules/**.md that mention the skill
  - hooks     ~/.claude/hooks/** scripts that mention the skill
  - sibling   other skills (~/.claude/skills/**) that mention the skill
              (1-hop only; transitive count is reported separately)
  - bin       ~/bin and ~/.local/bin scripts called from this skill's
              own files (delegated to script_discovery)

The walk is *strict* by default: it matches whole-word references like
``/prd``, ``prd.md``, or the absolute skill path, not substring matches
that would catch "spread", "prd_something_else", etc.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


CLAUDE_HOME = Path.home() / ".claude"
SKILLS_ROOT = CLAUDE_HOME / "skills"
RULES_ROOT = CLAUDE_HOME / "rules"
HOOKS_ROOT = CLAUDE_HOME / "hooks"

# Files we scan for references (text formats only).
SCANNABLE_EXTS = {".md", ".sh", ".py", ".json", ".yaml", ".yml", ".txt"}


@dataclass
class SkillCluster:
    """One-hop cluster around a single skill."""
    skill_name: str
    skill_path: Path
    rules: list[Path] = field(default_factory=list)
    hooks: list[Path] = field(default_factory=list)
    sibling_skills: list[Path] = field(default_factory=list)
    bin_scripts: list[Path] = field(default_factory=list)
    # Count of skills referenced transitively beyond the 1-hop sibling set.
    # Surfaced so the picker can show "+N transitive deps available".
    transitive_skill_count: int = 0

    def total_artifacts(self) -> int:
        return (
            len(self.rules)
            + len(self.hooks)
            + len(self.sibling_skills)
            + len(self.bin_scripts)
        )


def _reference_patterns(skill_name: str, skill_path: Path) -> list[re.Pattern[str]]:
    """Build a list of regexes that count as a real reference to this skill.

    A 'reference' is any of:
      - Slash-invocation: ``/skill_name`` followed by word-boundary
      - Filename: ``skill_name.md``
      - Directory: ``skill_name/`` (the skill's own folder)
      - Absolute path to the skill directory
    """
    safe = re.escape(skill_name)
    return [
        re.compile(rf"/{safe}\b"),
        re.compile(rf"\b{safe}\.md\b"),
        re.compile(rf"\b{safe}/"),
        re.compile(re.escape(str(skill_path))),
    ]


def _file_matches(path: Path, patterns: Iterable[re.Pattern[str]]) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return False
    return any(p.search(text) for p in patterns)


def _walk_text_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    if root.is_file():
        if root.suffix in SCANNABLE_EXTS:
            yield root
        return
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in SCANNABLE_EXTS:
            yield p


def _bin_scripts_called_from(skill_path: Path) -> list[Path]:
    """Find ~/bin/* scripts invoked by this skill's own files."""
    if not skill_path.exists():
        return []
    bin_dirs = [Path.home() / "bin", Path.home() / ".local" / "bin"]
    candidates = set()
    home = str(Path.home())
    abs_pat = re.compile(
        rf"({re.escape(home)}/(?:bin|\.local/bin)/[A-Za-z0-9_.-]+|~/(?:bin|\.local/bin)/[A-Za-z0-9_.-]+)"
    )
    for f in _walk_text_files(skill_path):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        for m in abs_pat.findall(text):
            name = Path(m.replace("~", home)).name
            for d in bin_dirs:
                cand = d / name
                if cand.exists():
                    candidates.add(cand.resolve())
                    break
    # Also bare-command refs (e.g., "session-search foo") — only if the bare
    # name exists in ~/bin and is not a common shell builtin.
    for f in _walk_text_files(skill_path):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        for d in bin_dirs:
            if not d.exists():
                continue
            for script in d.iterdir():
                if not script.is_file():
                    continue
                if re.search(rf"\b{re.escape(script.name)}\b", text):
                    candidates.add(script.resolve())
    return sorted(candidates)


def build_cluster(skill_name: str) -> SkillCluster | None:
    """Build a one-hop dependency cluster for the named skill.

    Returns None if the skill directory cannot be located under
    ~/.claude/skills/.
    """
    skill_dir = SKILLS_ROOT / skill_name
    skill_file = SKILLS_ROOT / f"{skill_name}.md"
    if skill_dir.is_dir():
        skill_path = skill_dir
    elif skill_file.is_file():
        skill_path = skill_file
    else:
        return None

    patterns = _reference_patterns(skill_name, skill_path)
    cluster = SkillCluster(skill_name=skill_name, skill_path=skill_path)

    # Rules
    for f in _walk_text_files(RULES_ROOT):
        if _file_matches(f, patterns):
            cluster.rules.append(f)

    # Hooks
    for f in _walk_text_files(HOOKS_ROOT):
        if _file_matches(f, patterns):
            cluster.hooks.append(f)

    # Sibling skills (other skills that reference this one — 1-hop)
    for sibling in SKILLS_ROOT.iterdir():
        if not sibling.exists() or sibling == skill_path:
            continue
        if sibling.is_dir():
            files = list(_walk_text_files(sibling))
        elif sibling.suffix == ".md":
            files = [sibling]
        else:
            continue
        if any(_file_matches(f, patterns) for f in files):
            cluster.sibling_skills.append(sibling)

    # Bin scripts called from this skill's own files
    cluster.bin_scripts = _bin_scripts_called_from(skill_path)

    # Transitive count: how many additional skills would be pulled in if we
    # recursed into the sibling cluster. We don't pull them; we just count.
    seen = {skill_name} | {s.stem if s.is_file() else s.name for s in cluster.sibling_skills}
    transitive = 0
    for sibling in cluster.sibling_skills:
        sub_name = sibling.stem if sibling.is_file() else sibling.name
        sub_cluster = _quick_sibling_count(sub_name, seen)
        transitive += sub_cluster
        seen.add(sub_name)
    cluster.transitive_skill_count = transitive

    return cluster


def _quick_sibling_count(skill_name: str, seen: set[str]) -> int:
    """Lightweight count of how many *new* sibling skills a given skill would
    pull in. Used only for the transitive-count summary; never expanded.
    """
    skill_dir = SKILLS_ROOT / skill_name
    skill_file = SKILLS_ROOT / f"{skill_name}.md"
    if skill_dir.is_dir():
        skill_path = skill_dir
    elif skill_file.is_file():
        skill_path = skill_file
    else:
        return 0
    patterns = _reference_patterns(skill_name, skill_path)
    new = 0
    for sibling in SKILLS_ROOT.iterdir():
        sub_name = sibling.stem if sibling.is_file() else sibling.name
        if sub_name in seen or sibling == skill_path:
            continue
        if sibling.is_dir():
            files = list(_walk_text_files(sibling))
        elif sibling.suffix == ".md":
            files = [sibling]
        else:
            continue
        if any(_file_matches(f, patterns) for f in files):
            new += 1
    return new
