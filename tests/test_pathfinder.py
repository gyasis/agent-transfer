"""Tests for agent_transfer.utils.pathfinder module."""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_transfer.utils.pathfinder import (
    PathProfile,
    PathProfileRegistry,
    Pathfinder,
    _reset_pathfinder,
    get_pathfinder,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the pathfinder singleton between tests."""
    _reset_pathfinder()
    yield
    _reset_pathfinder()


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Monkeypatch Path.home() to return a temp directory."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


@pytest.fixture
def pf(fake_home):
    """Return a fresh Pathfinder with a fake home directory."""
    return Pathfinder()


# ── T008: PathProfile creation and defaults ─────────────────────────


class TestPathProfile:
    def test_create_with_required_fields(self):
        p = PathProfile(slug="test", config_dir=".test")
        assert p.slug == "test"
        assert p.config_dir == ".test"
        assert p.agents_subdir is None
        assert p.skills_subdir is None
        assert p.hooks_subdir is None
        assert p.config_files == []
        assert p.executable_names == []
        assert p.project_level is False
        assert p.project_config_dir is None
        assert p.env_override_var is None
        assert p.search_paths == []

    def test_create_with_all_fields(self):
        p = PathProfile(
            slug="full",
            config_dir=".full",
            agents_subdir="agents",
            skills_subdir="skills",
            hooks_subdir="hooks",
            config_files=["a.json", "b.json"],
            executable_names=["full-cli"],
            project_level=True,
            project_config_dir=".full",
            env_override_var="FULL_CONFIG_DIR",
            search_paths=["/opt/full/bin"],
        )
        assert p.agents_subdir == "agents"
        assert p.config_files == ["a.json", "b.json"]
        assert p.project_level is True

    def test_default_list_fields_are_independent(self):
        """Ensure default mutable fields don't share state between instances."""
        a = PathProfile(slug="a", config_dir=".a")
        b = PathProfile(slug="b", config_dir=".b")
        a.config_files.append("test.json")
        assert b.config_files == []


# ── T009: PathProfileRegistry ───────────────────────────────────────


class TestPathProfileRegistry:
    def test_builtin_profiles_loaded(self):
        registry = PathProfileRegistry()
        slugs = registry.list_slugs()
        assert "claude-code" in slugs
        assert "codex" in slugs
        assert "gemini-cli" in slugs
        assert "goose" in slugs
        assert "opencode" in slugs
        assert len(slugs) == 5

    def test_get_existing(self):
        registry = PathProfileRegistry()
        profile = registry.get("claude-code")
        assert profile.slug == "claude-code"
        assert profile.config_dir == ".claude"

    def test_get_unknown_raises_key_error(self):
        registry = PathProfileRegistry()
        with pytest.raises(KeyError, match="Unknown platform 'nonexistent'"):
            registry.get("nonexistent")

    def test_key_error_lists_valid_slugs(self):
        registry = PathProfileRegistry()
        with pytest.raises(KeyError, match="claude-code"):
            registry.get("bad")

    def test_register_new_profile(self):
        registry = PathProfileRegistry()
        custom = PathProfile(slug="custom", config_dir=".custom")
        registry.register(custom)
        assert "custom" in registry.list_slugs()
        assert registry.get("custom").config_dir == ".custom"

    def test_register_replaces_existing(self):
        registry = PathProfileRegistry()
        replacement = PathProfile(
            slug="claude-code",
            config_dir=".claude-custom",
        )
        registry.register(replacement)
        assert registry.get("claude-code").config_dir == ".claude-custom"


# ── T010: Singleton behavior ────────────────────────────────────────


class TestSingleton:
    def test_get_pathfinder_returns_same_instance(self, fake_home):
        pf1 = get_pathfinder()
        pf2 = get_pathfinder()
        assert pf1 is pf2

    def test_reset_creates_new_instance(self, fake_home):
        pf1 = get_pathfinder()
        _reset_pathfinder()
        pf2 = get_pathfinder()
        assert pf1 is not pf2


# ── T021: Built-in profile resolution ──────────────────────────────


class TestBuiltinProfiles:
    def test_claude_code_dirs(self, pf, fake_home):
        assert pf.config_dir("claude-code") == fake_home / ".claude"
        assert pf.agents_dir("claude-code") == fake_home / ".claude" / "agents"
        assert pf.skills_dir("claude-code") == fake_home / ".claude" / "skills"
        assert pf.hooks_dir("claude-code") == fake_home / ".claude" / "hooks"
        assert pf.rules_dir("claude-code") == fake_home / ".claude" / "rules"

    def test_claude_code_home_root_configs(self, pf, fake_home):
        files = pf.home_root_config_files("claude-code")
        assert len(files) == 1
        assert fake_home / ".claude.json" in files

    def test_claude_code_instruction_files(self, pf, fake_home):
        files = pf.instruction_files("claude-code")
        assert len(files) == 1
        assert fake_home / ".claude" / "CLAUDE.md" in files

    def test_claude_code_config_files(self, pf, fake_home):
        files = pf.config_files("claude-code")
        assert len(files) == 4
        assert fake_home / ".claude" / "mcp.json" in files
        assert fake_home / ".claude" / "settings.json" in files
        assert fake_home / ".claude" / "settings.local.json" in files
        assert fake_home / ".claude" / "keybindings.json" in files

    def test_codex_dirs(self, pf, fake_home):
        assert pf.config_dir("codex") == fake_home / ".codex"
        assert pf.agents_dir("codex") is None
        assert pf.skills_dir("codex") is None
        assert pf.hooks_dir("codex") is None

    def test_gemini_cli_dirs(self, pf, fake_home):
        assert pf.config_dir("gemini-cli") == fake_home / ".gemini"
        assert pf.agents_dir("gemini-cli") == fake_home / ".gemini" / "agents"
        assert pf.skills_dir("gemini-cli") == fake_home / ".gemini" / "skills"
        assert pf.hooks_dir("gemini-cli") is None

    def test_goose_dirs(self, pf, fake_home):
        assert pf.config_dir("goose") == fake_home / ".config" / "goose"
        assert pf.agents_dir("goose") is None
        assert pf.skills_dir("goose") == fake_home / ".config" / "goose" / "recipes"
        assert pf.hooks_dir("goose") is None

    def test_opencode_dirs(self, pf, fake_home):
        assert pf.config_dir("opencode") == fake_home / ".opencode"
        assert pf.agents_dir("opencode") == fake_home / ".opencode" / "agents"
        assert pf.skills_dir("opencode") == fake_home / ".opencode" / "plugins"
        assert pf.hooks_dir("opencode") is None

    def test_supported_platforms(self, pf):
        platforms = pf.supported_platforms()
        assert platforms == ["claude-code", "codex", "gemini-cli", "goose", "opencode"]


# ── T022: None returns for missing directory types ──────────────────


class TestNoneReturns:
    def test_codex_has_no_agents(self, pf):
        assert pf.agents_dir("codex") is None

    def test_codex_has_no_skills(self, pf):
        assert pf.skills_dir("codex") is None

    def test_codex_has_no_hooks(self, pf):
        assert pf.hooks_dir("codex") is None

    def test_goose_has_no_agents(self, pf):
        assert pf.agents_dir("goose") is None

    def test_goose_has_no_hooks(self, pf):
        assert pf.hooks_dir("goose") is None

    def test_gemini_has_no_hooks(self, pf):
        assert pf.hooks_dir("gemini-cli") is None

    def test_opencode_has_no_hooks(self, pf):
        assert pf.hooks_dir("opencode") is None


# ── T023: Project-level resolution ──────────────────────────────────


class TestProjectLevel:
    def test_finds_project_agents_dir(self, pf, tmp_path):
        project_dir = tmp_path / "my-project"
        agents = project_dir / ".claude" / "agents"
        agents.mkdir(parents=True)

        result = pf.project_agents_dir("claude-code", start_dir=project_dir)
        assert result == agents

    def test_finds_project_skills_dir(self, pf, tmp_path):
        project_dir = tmp_path / "my-project"
        skills = project_dir / ".claude" / "skills"
        skills.mkdir(parents=True)

        result = pf.project_skills_dir("claude-code", start_dir=project_dir)
        assert result == skills

    def test_searches_upward(self, pf, tmp_path):
        # Create .claude/agents at root level
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        # Start from a nested subdirectory
        nested = tmp_path / "src" / "deep" / "nested"
        nested.mkdir(parents=True)

        result = pf.project_agents_dir("claude-code", start_dir=nested)
        assert result == tmp_path / ".claude" / "agents"

    def test_returns_none_when_not_found(self, pf, tmp_path):
        result = pf.project_agents_dir("claude-code", start_dir=tmp_path)
        assert result is None

    def test_returns_none_for_non_project_platform(self, pf, tmp_path):
        # Goose doesn't support project-level dirs
        result = pf.project_agents_dir("goose", start_dir=tmp_path)
        assert result is None

    def test_respects_search_depth(self, tmp_path):
        pf = Pathfinder(project_search_depth=1)
        # Create .claude/agents 3 levels up
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)

        result = pf.project_agents_dir("claude-code", start_dir=nested)
        assert result is None  # Too deep


# ── T024: all_agents_dirs and all_skills_dirs ───────────────────────


class TestAllDirs:
    def test_all_agents_dirs_user_only(self, pf, fake_home, tmp_path, monkeypatch):
        # Use a dir with no .claude/ to avoid project-level hit
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)
        pf.clear_cache()
        result = pf.all_agents_dirs("claude-code")
        assert len(result) == 1
        assert result[0] == (fake_home / ".claude" / "agents", "user")

    def test_all_agents_dirs_user_and_project(self, pf, fake_home, tmp_path):
        # Create a project-level agents dir in cwd
        project_agents = Path.cwd() / ".claude" / "agents"
        project_agents.mkdir(parents=True, exist_ok=True)
        try:
            result = pf.all_agents_dirs("claude-code")
            scopes = [s for _, s in result]
            assert "user" in scopes
            # Project might be found depending on cwd
        finally:
            # Cleanup
            import shutil

            cleanup = Path.cwd() / ".claude"
            if cleanup.exists():
                shutil.rmtree(cleanup)

    def test_all_skills_dirs_returns_tuples(self, pf, fake_home):
        result = pf.all_skills_dirs("claude-code")
        assert len(result) >= 1
        path, scope = result[0]
        assert isinstance(path, Path)
        assert scope == "user"

    def test_all_agents_dirs_empty_for_goose(self, pf, fake_home):
        result = pf.all_agents_dirs("goose")
        assert result == []  # Goose has no agents dir


# ── T025: Third-party profile registration ──────────────────────────


class TestThirdPartyProfile:
    def test_register_and_resolve(self, pf, fake_home):
        custom = PathProfile(
            slug="my-agent",
            config_dir=".my-agent",
            agents_subdir="bots",
            skills_subdir="tools",
            hooks_subdir=None,
            config_files=["config.yaml"],
            executable_names=["my-agent"],
        )
        pf.register_profile(custom)

        assert "my-agent" in pf.supported_platforms()
        assert pf.config_dir("my-agent") == fake_home / ".my-agent"
        assert pf.agents_dir("my-agent") == fake_home / ".my-agent" / "bots"
        assert pf.skills_dir("my-agent") == fake_home / ".my-agent" / "tools"
        assert pf.hooks_dir("my-agent") is None
        assert pf.config_files("my-agent") == [fake_home / ".my-agent" / "config.yaml"]

    def test_register_clears_cache(self, pf, fake_home):
        # Populate cache
        pf.config_dir("claude-code")
        assert len(pf._cache) > 0

        # Register new profile — cache should be cleared
        pf.register_profile(PathProfile(slug="new", config_dir=".new"))
        assert len(pf._cache) == 0


# ── T028-T031: Executable discovery ─────────────────────────────────


class TestFindExecutable:
    def test_finds_via_shutil_which(self, pf, monkeypatch):
        monkeypatch.setattr(
            "agent_transfer.utils.pathfinder.shutil.which",
            lambda name: "/usr/local/bin/claude" if name == "claude" else None,
        )
        result = pf.find_executable("claude-code")
        assert result == Path("/usr/local/bin/claude")

    def test_falls_back_to_npm_global(self, pf, fake_home, monkeypatch):
        monkeypatch.setattr(
            "agent_transfer.utils.pathfinder.shutil.which",
            lambda name: None,
        )
        # Create a fake executable in npm global path
        npm_bin = fake_home / ".npm-global" / "bin"
        npm_bin.mkdir(parents=True)
        exe = npm_bin / "claude"
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)

        result = pf.find_executable("claude-code")
        assert result == exe

    def test_returns_none_when_not_found(self, pf, monkeypatch):
        monkeypatch.setattr(
            "agent_transfer.utils.pathfinder.shutil.which",
            lambda name: None,
        )
        result = pf.find_executable("claude-code")
        assert result is None

    def test_caches_result(self, pf, monkeypatch):
        call_count = [0]

        def mock_which(name):
            call_count[0] += 1
            return "/usr/bin/claude"

        monkeypatch.setattr(
            "agent_transfer.utils.pathfinder.shutil.which", mock_which
        )

        pf.find_executable("claude-code")
        pf.find_executable("claude-code")
        assert call_count[0] == 1  # Only called once

    def test_clear_cache_allows_rediscovery(self, pf, monkeypatch):
        call_count = [0]

        def mock_which(name):
            call_count[0] += 1
            return "/usr/bin/claude"

        monkeypatch.setattr(
            "agent_transfer.utils.pathfinder.shutil.which", mock_which
        )

        pf.find_executable("claude-code")
        pf.clear_cache()
        pf.find_executable("claude-code")
        assert call_count[0] == 2  # Called again after cache clear

    def test_skips_npm_for_non_node_platforms(self, pf, fake_home, monkeypatch):
        """Goose should not check npm/nvm paths."""
        monkeypatch.setattr(
            "agent_transfer.utils.pathfinder.shutil.which",
            lambda name: None,
        )
        # Create fake goose in npm path (should NOT be found)
        npm_bin = fake_home / ".npm-global" / "bin"
        npm_bin.mkdir(parents=True)
        exe = npm_bin / "goose"
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)

        result = pf.find_executable("goose")
        assert result is None  # npm path skipped for goose


# ── T033-T035: Path remapping ───────────────────────────────────────


class TestRemapPath:
    def test_successful_remap(self, pf):
        result = pf.remap_path(
            Path("/home/alice/.claude/hooks/pre-commit.sh"),
            source_home="/home/alice",
            target_home="/home/bob",
        )
        assert result == Path("/home/bob/.claude/hooks/pre-commit.sh")

    def test_noop_relative_path(self, pf):
        original = Path("relative/path.txt")
        result = pf.remap_path(original, "/home/alice", "/home/bob")
        assert result == original

    def test_noop_no_prefix_match(self, pf):
        original = Path("/opt/data/file.txt")
        result = pf.remap_path(original, "/home/alice", "/home/bob")
        assert result == original

    def test_noop_already_correct(self, pf):
        original = Path("/home/bob/.claude/hooks/pre-commit.sh")
        result = pf.remap_path(original, "/home/bob", "/home/bob")
        assert result == original

    def test_embedded_home_not_matched(self, pf):
        """A path like /opt/home/alice/... should NOT be remapped."""
        original = Path("/opt/home/alice/data.txt")
        result = pf.remap_path(original, "/home/alice", "/home/bob")
        assert result == original

    def test_exact_home_path(self, pf):
        """Remapping the home directory itself."""
        result = pf.remap_path(
            Path("/home/alice"),
            source_home="/home/alice",
            target_home="/home/bob",
        )
        assert result == Path("/home/bob")

    def test_cross_os_windows_to_linux(self, pf):
        """Windows-style paths should be remapped correctly on Linux."""
        result = pf.remap_path(
            Path("C:\\Users\\alice\\.claude\\mcp.json"),
            source_home="C:\\Users\\alice",
            target_home="/home/bob",
        )
        assert str(result) == "/home/bob/.claude/mcp.json"


# ── T037-T039: Environment variable overrides ───────────────────────


class TestEnvOverrides:
    def test_config_dir_uses_env_override(self, pf, fake_home, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/custom/claude")
        pf.clear_cache()
        assert pf.config_dir("claude-code") == Path("/custom/claude")

    def test_override_propagates_to_agents_dir(self, pf, fake_home, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/custom/claude")
        pf.clear_cache()
        assert pf.agents_dir("claude-code") == Path("/custom/claude/agents")

    def test_override_propagates_to_skills_dir(self, pf, fake_home, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/custom/claude")
        pf.clear_cache()
        assert pf.skills_dir("claude-code") == Path("/custom/claude/skills")

    def test_override_propagates_to_hooks_dir(self, pf, fake_home, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/custom/claude")
        pf.clear_cache()
        assert pf.hooks_dir("claude-code") == Path("/custom/claude/hooks")

    def test_override_propagates_to_config_files(self, pf, fake_home, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/custom/claude")
        pf.clear_cache()
        files = pf.config_files("claude-code")
        assert Path("/custom/claude/mcp.json") in files

    def test_fallback_when_no_env(self, pf, fake_home, monkeypatch):
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        assert pf.config_dir("claude-code") == fake_home / ".claude"


# ── T041-T043: Cross-platform translation ───────────────────────────


class TestTranslatePath:
    def test_claude_skills_to_goose(self, pf, fake_home):
        translated, warning = pf.translate_path(
            "~/.claude/skills/my-skill/",
            from_platform="claude-code",
            to_platform="goose",
        )
        assert warning is None
        assert translated == "~/.config/goose/recipes/my-skill/"

    def test_claude_config_to_opencode(self, pf, fake_home):
        translated, warning = pf.translate_path(
            "~/.claude/agents/my-agent",
            from_platform="claude-code",
            to_platform="opencode",
        )
        assert warning is None
        assert translated == "~/.opencode/agents/my-agent"

    def test_unrecognized_path_returns_warning(self, pf, fake_home):
        translated, warning = pf.translate_path(
            "/random/path/file.txt",
            from_platform="claude-code",
            to_platform="goose",
        )
        assert warning is not None
        assert "does not match" in warning
        assert translated == "/random/path/file.txt"

    def test_target_has_no_equivalent(self, pf, fake_home):
        """Translating agents from Claude Code to Goose (Goose has no agents dir)."""
        translated, warning = pf.translate_path(
            "~/.claude/agents/my-agent",
            from_platform="claude-code",
            to_platform="goose",
        )
        assert warning is not None
        assert "no equivalent" in warning

    def test_all_platforms_config_translation(self, pf, fake_home):
        """Config dir translation should work between all platforms."""
        platforms = pf.supported_platforms()
        for source in platforms:
            source_profile = pf.registry.get(source)
            source_path = "~/" + source_profile.config_dir + "/some-file"
            for target in platforms:
                if source == target:
                    continue
                translated, warning = pf.translate_path(
                    source_path,
                    from_platform=source,
                    to_platform=target,
                )
                assert warning is None, (
                    f"Translation {source} -> {target} failed: {warning}"
                )

    def test_embedded_tilde_not_expanded(self, pf, fake_home):
        """Only leading ~ should be expanded, not embedded tildes."""
        translated, warning = pf.translate_path(
            "~/.claude/skills/~/evil",
            from_platform="claude-code",
            to_platform="goose",
        )
        # The embedded ~/evil should remain as literal ~/evil in output
        assert warning is None
        # Key: the embedded ~ must NOT be expanded to a home path
        home_str = str(fake_home)
        assert home_str + "/evil" not in translated


# ── Utility methods ─────────────────────────────────────────────────


class TestUtilities:
    def test_validate_path_existing(self, pf, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        assert pf.validate_path(test_file) is True

    def test_validate_path_nonexistent(self, pf, tmp_path):
        assert pf.validate_path(tmp_path / "nope") is False

    def test_ensure_dir_creates(self, pf, tmp_path):
        target = tmp_path / "a" / "b" / "c"
        result = pf.ensure_dir(target)
        assert target.is_dir()
        assert result == target

    def test_ensure_dir_existing(self, pf, tmp_path):
        result = pf.ensure_dir(tmp_path)
        assert result == tmp_path
