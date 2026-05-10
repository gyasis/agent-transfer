"""G12 — capability registry takes precedence over discovery.

Pre-fix bug: `--capability X` was free text. Two machines with the same
capability name composed different bundles based on local file contents,
so `compose → ship → re-compose` could not round-trip identity.

Post-fix: `~/.claude/capabilities/<name>.yaml` declares the canonical
asset list. When present, compose() uses it directly; otherwise falls
back to discovery.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agent_transfer.bridge.capability_registry import (
    RegistryError,
    load_registered,
)
from agent_transfer.bridge.compose import compose


def _write_registry(home: Path, name: str, body: str) -> Path:
    reg_dir = home / ".claude" / "capabilities"
    reg_dir.mkdir(parents=True, exist_ok=True)
    p = reg_dir / f"{name}.yaml"
    p.write_text(textwrap.dedent(body).lstrip())
    return p


def _seed_skill(home: Path, slug: str) -> Path:
    skills = home / ".claude" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    p = skills / f"{slug}.md"
    p.write_text(f"# {slug}\n")
    return p


def _seed_skill_pkg(home: Path, slug: str) -> Path:
    pkg = home / ".claude" / "skills" / slug
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "SKILL.md").write_text(f"# {slug}\n")
    (pkg / "scripts").mkdir()
    (pkg / "scripts" / "go.sh").write_text("#!/bin/sh\n")
    return pkg


def _seed_rule(home: Path, name: str) -> Path:
    rules = home / ".claude" / "rules" / "tools"
    rules.mkdir(parents=True, exist_ok=True)
    p = rules / f"{name}.md"
    p.write_text(f"# {name} rule\n")
    return p


def test_g12_registry_takes_precedence_over_discovery(tmp_path):
    home = tmp_path / "home"
    # Seed two skills — only one is in the registry.
    _seed_skill(home, "sio-scan")
    _seed_skill(home, "sio-suggest")
    _seed_rule(home, "sio")

    # Registry declares ONLY sio-scan + sio rule, NOT sio-suggest.
    _write_registry(home, "sio", """
        name: sio
        description: SIO subset
        intent: Test registry precedence
        assets:
          - ~/.claude/skills/sio-scan.md
          - ~/.claude/rules/tools/sio.md
    """)

    cap = compose("sio", home=home)
    rels = {a.dest_path for a in cap.assets}

    assert rels == {
        "~/.claude/skills/sio-scan.md",
        "~/.claude/rules/tools/sio.md",
    }, "registry must be authoritative; discovery's sio-suggest must NOT be in the bundle"


def test_g12_registry_carries_smoke_commands_and_deps(tmp_path):
    home = tmp_path / "home"
    _seed_skill(home, "sio-scan")

    _write_registry(home, "sio", """
        name: sio
        description: SIO with smoke
        intent: Test smoke + deps
        assets:
          - ~/.claude/skills/sio-scan.md
        dependencies:
          - sio
        smoke_commands:
          - sio --version
          - sio status
    """)

    cap = compose("sio", home=home)
    assert cap.dependencies == ["sio"]
    assert cap.smoke_commands == ["sio --version", "sio status"]
    assert cap.description == "SIO with smoke"


def test_g12_registry_dir_asset_pulls_subtree(tmp_path):
    home = tmp_path / "home"
    _seed_skill_pkg(home, "sio-scan")

    _write_registry(home, "sio", """
        name: sio
        description: SIO with package
        intent: Test dir expansion
        assets:
          - ~/.claude/skills/sio-scan/
    """)

    cap = compose("sio", home=home)
    rels = {a.dest_path for a in cap.assets}
    assert "~/.claude/skills/sio-scan/SKILL.md" in rels
    assert "~/.claude/skills/sio-scan/scripts/go.sh" in rels


def test_g12_no_registry_falls_back_to_discovery(tmp_path):
    home = tmp_path / "home"
    _seed_skill(home, "sio-scan")
    # No registry file written.

    cap = compose("sio-scan", home=home)
    rels = {a.dest_path for a in cap.assets}
    assert "~/.claude/skills/sio-scan.md" in rels


def test_g12_malformed_yaml_raises(tmp_path):
    home = tmp_path / "home"
    _write_registry(home, "sio", """
        name: sio
        : : :
    """)
    with pytest.raises(RegistryError, match="Malformed YAML"):
        load_registered("sio", home=home)


def test_g12_missing_asset_path_raises(tmp_path):
    home = tmp_path / "home"
    _write_registry(home, "sio", """
        name: sio
        description: x
        intent: x
        assets:
          - ~/.claude/skills/does-not-exist.md
    """)
    with pytest.raises(RegistryError, match="does not exist"):
        compose("sio", home=home)


def test_b_rejects_absolute_path_outside_home(tmp_path):
    """B (F2) — registry asset path must be inside $HOME."""
    home = tmp_path / "home"
    home.mkdir()
    _write_registry(home, "evil", """
        name: evil
        description: x
        intent: x
        assets:
          - /etc/shadow
    """)
    with pytest.raises(RegistryError, match="outside .HOME"):
        compose("evil", home=home)


def test_b_rejects_dotdot_traversal(tmp_path):
    """B (F2) — `..` segments rejected even if they happen to stay in $HOME."""
    home = tmp_path / "home"
    home.mkdir()
    (home / "innocent.md").write_text("ok")
    _write_registry(home, "trav", """
        name: trav
        description: x
        intent: x
        assets:
          - ~/../home/innocent.md
    """)
    # Using a relative-form home, so we adjust the YAML format if needed.
    # The literal "~/.." path is what we want to reject.
    with pytest.raises(RegistryError, match="may not contain"):
        compose("trav", home=home)


def test_b_rejects_symlinked_asset(tmp_path):
    """B (F2) — symlinks under registry-declared paths are not followed."""
    home = tmp_path / "home"
    home.mkdir()
    target_outside = tmp_path / "outside"
    target_outside.mkdir()
    (target_outside / "secret.md").write_text("SECRET")
    link = home / "link.md"
    link.symlink_to(target_outside / "secret.md")

    _write_registry(home, "lk", """
        name: lk
        description: x
        intent: x
        assets:
          - ~/link.md
    """)
    with pytest.raises(RegistryError, match="symlink"):
        compose("lk", home=home)


def test_b_rejects_symlinked_subpath_in_dir(tmp_path):
    """B (F2) — dir asset whose child is a symlink rejects."""
    home = tmp_path / "home"
    pkg = home / ".claude" / "skills" / "x"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text("# x\n")

    target = tmp_path / "outside" / "evil.sh"
    target.parent.mkdir()
    target.write_text("#!/bin/sh\nrm -rf /\n")
    (pkg / "evil-link.sh").symlink_to(target)

    _write_registry(home, "x", """
        name: x
        description: x
        intent: x
        assets:
          - ~/.claude/skills/x/
    """)
    with pytest.raises(RegistryError, match="symlink"):
        compose("x", home=home)


def test_c_provenance_stamped_on_registry_compose(tmp_path):
    """C (B G12 adjacent) — registry-composed Capability records source path + sha."""
    import hashlib

    home = tmp_path / "home"
    _seed_skill(home, "sio-scan")

    body = """
        name: sio
        description: SIO with provenance
        intent: Test C
        assets:
          - ~/.claude/skills/sio-scan.md
    """
    reg_path = _write_registry(home, "sio", body)
    expected_sha = hashlib.sha256(reg_path.read_bytes()).hexdigest()

    cap = compose("sio", home=home)
    assert cap.registered_via is not None
    assert cap.registered_via.registry_path == "~/.claude/capabilities/sio.yaml"
    assert cap.registered_via.yaml_sha256 == expected_sha


def test_c_no_provenance_on_discovery_compose(tmp_path):
    """Discovery path (no registry) leaves registered_via=None."""
    home = tmp_path / "home"
    _seed_skill(home, "sio-scan")
    cap = compose("sio-scan", home=home)
    assert cap.registered_via is None


def test_g12_name_mismatch_raises(tmp_path):
    home = tmp_path / "home"
    _write_registry(home, "sio", """
        name: not-sio
        description: x
        intent: x
        assets:
          - ~/.claude/skills/x.md
    """)
    with pytest.raises(RegistryError, match="filename stem"):
        load_registered("sio", home=home)
