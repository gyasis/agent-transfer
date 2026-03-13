"""Unit tests for the preflight inventory collector and manifest I/O.

Tests cover:
- collect_inventory() with empty inputs
- collect_inventory() with agent .md files containing MCP tool references
- collect_inventory() with skill directories containing scripts
- collect_inventory() with skill directories containing .preflight.yml
- write_manifest() + read_manifest() round-trip
- read_manifest_from_archive() with valid archive
- read_manifest_from_archive() with legacy archive (no manifest)
- deduplicate_dependencies() merging logic

Python >= 3.8 compatible.
"""

from __future__ import annotations

import json
import platform
import tarfile
from dataclasses import asdict
from pathlib import Path

import pytest

from agent_transfer.utils.preflight.collector import (
    collect_inventory,
    deduplicate_dependencies,
)
from agent_transfer.utils.preflight.manifest import (
    CliToolDep,
    ContentsInventory,
    DependencyGraph,
    EnvVarDep,
    McpServerDep,
    PackageDep,
    SkillTreeDep,
    TransferManifest,
    read_manifest,
    read_manifest_from_archive,
    write_manifest,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agent_md_with_mcp(tmp_path):
    """Create a mock agent .md file that references MCP tool declarations."""
    md_file = tmp_path / "my-agent.md"
    md_file.write_text(
        "# My Agent\n"
        "\n"
        "This agent uses several MCP tools:\n"
        "- mcp__graphiti__search_nodes for memory\n"
        "- mcp__graphiti__add_memory for saving\n"
        "- mcp__playwright__browser_navigate for browsing\n"
        "- mcp__playwright__browser_snapshot for screenshots\n"
        "- mcp__context7-mcp__resolve-library-id for docs\n"
        "\n"
        "Some regular text that should not match.\n",
        encoding="utf-8",
    )
    return md_file


@pytest.fixture
def skill_dir_with_scripts(tmp_path):
    """Create a mock skill directory containing shell and Python scripts."""
    skill = tmp_path / "my-skill"
    skill.mkdir()

    # A shell script that invokes CLI tools
    sh_script = skill / "run.sh"
    sh_script.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "\n"
        "jq '.data' input.json\n"
        "curl -s https://example.com/api\n"
        "echo $MY_API_KEY\n"
        "echo ${SOME_SECRET}\n",
        encoding="utf-8",
    )

    # A Python script that imports third-party packages
    py_script = skill / "process.py"
    py_script.write_text(
        "import os\n"
        "import json\n"
        "from pathlib import Path\n"
        "\n"
        "import requests\n"
        "from rich.console import Console\n"
        "\n"
        "api_key = os.environ.get('API_TOKEN')\n",
        encoding="utf-8",
    )

    return skill


@pytest.fixture
def skill_dir_with_preflight(tmp_path):
    """Create a mock skill directory containing a .preflight.yml file."""
    skill = tmp_path / "preflight-skill"
    skill.mkdir()

    preflight = skill / ".preflight.yml"
    preflight.write_text(
        "dependencies:\n"
        "  cli_tools:\n"
        "    - name: ffmpeg\n"
        "      install_hint: apt install ffmpeg\n"
        "      version_hint: '>=5.0'\n"
        "    - name: sox\n"
        "  env_vars:\n"
        "    - name: OPENAI_API_KEY\n"
        "      description: Key for OpenAI API access\n"
        "    - name: HF_TOKEN\n"
        "  packages:\n"
        "    - name: torch\n"
        "      ecosystem: python\n"
        "    - name: numpy\n"
        "notes:\n"
        "  - Requires GPU for optimal performance\n",
        encoding="utf-8",
    )

    # Also add a simple script so the skill has scannable content
    script = skill / "main.sh"
    script.write_text(
        "#!/bin/bash\n"
        "git clone https://example.com/repo.git\n",
        encoding="utf-8",
    )

    return skill


@pytest.fixture
def manifest_with_data():
    """Build a TransferManifest with representative data for round-trip tests."""
    return TransferManifest(
        manifest_version="2.0",
        created_at="2026-03-11T00:00:00+00:00",
        source_platform="claude-code",
        source_os="linux",
        source_arch="x86_64",
        source_home="/home/tester",
        contents=ContentsInventory(
            agents=["agent-a.md", "agent-b.md"],
            skills=["skill-one", "skill-two"],
            hooks=["pre-commit.sh"],
            configs=["mcp.json"],
        ),
        dependencies=DependencyGraph(
            mcp_servers=[
                McpServerDep(
                    id="graphiti",
                    install_type="git-repo-python-venv",
                    repo_url="https://github.com/example/graphiti.git",
                    runtime="python",
                    auth_required=True,
                    env_vars=["GRAPHITI_TOKEN"],
                    required_by=["agent-a"],
                ),
            ],
            cli_tools=[
                CliToolDep(
                    name="jq",
                    version_hint=">=1.6",
                    install_hint="apt install jq",
                    required_by=["skill-one"],
                ),
                CliToolDep(
                    name="curl",
                    required_by=["skill-one"],
                ),
            ],
            env_vars=[
                EnvVarDep(
                    name="MY_SECRET",
                    description="A test secret",
                    critical=True,
                    required_by=["skill-one"],
                ),
            ],
            python_packages=[
                PackageDep(
                    name="requests",
                    ecosystem="python",
                    required_by=["skill-one"],
                ),
            ],
            skill_trees=[
                SkillTreeDep(
                    name="skill-one",
                    install_path="/tmp/skills/skill-one",
                    system_deps=["jq"],
                ),
            ],
        ),
    )


# ---------------------------------------------------------------------------
# 1. collect_inventory() with empty inputs
# ---------------------------------------------------------------------------


class TestCollectInventoryEmpty:
    """collect_inventory() with no agents, skills, hooks, or configs."""

    def test_returns_transfer_manifest(self):
        result = collect_inventory(
            agents=[], skills=[], hooks=[], configs=[]
        )
        assert isinstance(result, TransferManifest)

    def test_manifest_version_is_2_0(self):
        result = collect_inventory(
            agents=[], skills=[], hooks=[], configs=[]
        )
        assert result.manifest_version == "2.0"

    def test_source_platform_defaults_to_claude_code(self):
        result = collect_inventory(
            agents=[], skills=[], hooks=[], configs=[]
        )
        assert result.source_platform == "claude-code"

    def test_custom_platform_propagates(self):
        result = collect_inventory(
            agents=[], skills=[], hooks=[], configs=[],
            platform="windsurf",
        )
        assert result.source_platform == "windsurf"

    def test_populates_source_os(self):
        result = collect_inventory(
            agents=[], skills=[], hooks=[], configs=[]
        )
        assert result.source_os == platform.system().lower()

    def test_populates_source_arch(self):
        result = collect_inventory(
            agents=[], skills=[], hooks=[], configs=[]
        )
        assert result.source_arch == platform.machine()

    def test_populates_source_home(self):
        result = collect_inventory(
            agents=[], skills=[], hooks=[], configs=[]
        )
        assert result.source_home == str(Path.home())

    def test_created_at_is_nonempty_iso_timestamp(self):
        result = collect_inventory(
            agents=[], skills=[], hooks=[], configs=[]
        )
        assert result.created_at
        # Basic shape check for ISO 8601
        assert "T" in result.created_at

    def test_empty_contents_inventory(self):
        result = collect_inventory(
            agents=[], skills=[], hooks=[], configs=[]
        )
        assert result.contents.agents == []
        assert result.contents.skills == []
        assert result.contents.hooks == []
        assert result.contents.configs == []

    def test_empty_dependency_graph(self):
        result = collect_inventory(
            agents=[], skills=[], hooks=[], configs=[]
        )
        deps = result.dependencies
        assert deps.mcp_servers == []
        assert deps.cli_tools == []
        assert deps.env_vars == []
        assert deps.python_packages == []
        assert deps.git_repos == []
        assert deps.compiled_binaries == []
        assert deps.skill_trees == []
        assert deps.docker == []
        assert deps.sourced_files == []


# ---------------------------------------------------------------------------
# 2. collect_inventory() with agent .md containing MCP tool references
# ---------------------------------------------------------------------------


class TestCollectInventoryAgentMcp:
    """Agent markdown files with mcp__<server>__<tool> references."""

    def test_extracts_mcp_server_ids(self, agent_md_with_mcp):
        result = collect_inventory(
            agents=[agent_md_with_mcp],
            skills=[], hooks=[], configs=[],
        )
        server_ids = {s.id for s in result.dependencies.mcp_servers}
        assert "graphiti" in server_ids
        assert "playwright" in server_ids

    def test_extracts_context7_mcp_id(self, agent_md_with_mcp):
        result = collect_inventory(
            agents=[agent_md_with_mcp],
            skills=[], hooks=[], configs=[],
        )
        server_ids = {s.id for s in result.dependencies.mcp_servers}
        assert "context7-mcp" in server_ids

    def test_deduplicates_server_ids(self, agent_md_with_mcp):
        """graphiti appears twice (search_nodes and add_memory) but should
        produce only one McpServerDep entry."""
        result = collect_inventory(
            agents=[agent_md_with_mcp],
            skills=[], hooks=[], configs=[],
        )
        graphiti_deps = [
            s for s in result.dependencies.mcp_servers if s.id == "graphiti"
        ]
        assert len(graphiti_deps) == 1

    def test_required_by_tracks_agent_stem(self, agent_md_with_mcp):
        result = collect_inventory(
            agents=[agent_md_with_mcp],
            skills=[], hooks=[], configs=[],
        )
        graphiti = next(
            s for s in result.dependencies.mcp_servers if s.id == "graphiti"
        )
        assert "my-agent" in graphiti.required_by

    def test_agent_name_in_contents(self, agent_md_with_mcp):
        result = collect_inventory(
            agents=[agent_md_with_mcp],
            skills=[], hooks=[], configs=[],
        )
        assert "my-agent.md" in result.contents.agents

    def test_nonexistent_agent_path_skipped(self, tmp_path):
        fake_path = tmp_path / "does-not-exist.md"
        result = collect_inventory(
            agents=[fake_path],
            skills=[], hooks=[], configs=[],
        )
        assert result.contents.agents == []
        assert result.dependencies.mcp_servers == []

    def test_multiple_agents_merge_server_required_by(self, tmp_path):
        """Two agents referencing the same MCP server should merge required_by."""
        agent_a = tmp_path / "alpha.md"
        agent_a.write_text("Use mcp__graphiti__search_nodes here.\n")

        agent_b = tmp_path / "beta.md"
        agent_b.write_text("Also use mcp__graphiti__add_memory here.\n")

        result = collect_inventory(
            agents=[agent_a, agent_b],
            skills=[], hooks=[], configs=[],
        )
        graphiti = next(
            s for s in result.dependencies.mcp_servers if s.id == "graphiti"
        )
        assert "alpha" in graphiti.required_by
        assert "beta" in graphiti.required_by


# ---------------------------------------------------------------------------
# 3. collect_inventory() with skill directory containing scripts
# ---------------------------------------------------------------------------


class TestCollectInventorySkillScripts:
    """Skill directories containing .sh and .py scripts with tool references."""

    def test_detects_cli_tools_from_shell_script(self, skill_dir_with_scripts):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_scripts], hooks=[], configs=[],
        )
        cli_names = {t.name for t in result.dependencies.cli_tools}
        assert "jq" in cli_names
        assert "curl" in cli_names

    def test_detects_env_vars_from_shell_script(self, skill_dir_with_scripts):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_scripts], hooks=[], configs=[],
        )
        env_names = {e.name for e in result.dependencies.env_vars}
        assert "MY_API_KEY" in env_names
        assert "SOME_SECRET" in env_names

    def test_detects_python_packages(self, skill_dir_with_scripts):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_scripts], hooks=[], configs=[],
        )
        pkg_names = {p.name for p in result.dependencies.python_packages}
        assert "requests" in pkg_names
        assert "rich" in pkg_names

    def test_does_not_include_stdlib_as_packages(self, skill_dir_with_scripts):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_scripts], hooks=[], configs=[],
        )
        pkg_names = {p.name for p in result.dependencies.python_packages}
        # os, json, pathlib are stdlib -- should not appear
        assert "os" not in pkg_names
        assert "json" not in pkg_names
        assert "pathlib" not in pkg_names

    def test_detects_env_vars_from_python_os_environ(self, skill_dir_with_scripts):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_scripts], hooks=[], configs=[],
        )
        env_names = {e.name for e in result.dependencies.env_vars}
        assert "API_TOKEN" in env_names

    def test_skill_name_in_contents(self, skill_dir_with_scripts):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_scripts], hooks=[], configs=[],
        )
        assert "my-skill" in result.contents.skills

    def test_skill_tree_created(self, skill_dir_with_scripts):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_scripts], hooks=[], configs=[],
        )
        tree_names = {t.name for t in result.dependencies.skill_trees}
        assert "my-skill" in tree_names

    def test_nonexistent_skill_dir_skipped(self, tmp_path):
        fake = tmp_path / "no-such-skill"
        result = collect_inventory(
            agents=[], skills=[fake], hooks=[], configs=[],
        )
        assert result.contents.skills == []


# ---------------------------------------------------------------------------
# 4. collect_inventory() with skill directory containing .preflight.yml
# ---------------------------------------------------------------------------


class TestCollectInventoryPreflight:
    """Skill directories with .preflight.yml declarations."""

    def test_preflight_cli_tools_detected(self, skill_dir_with_preflight):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_preflight], hooks=[], configs=[],
        )
        cli_names = {t.name for t in result.dependencies.cli_tools}
        assert "ffmpeg" in cli_names
        assert "sox" in cli_names

    def test_preflight_cli_tool_hints_preserved(self, skill_dir_with_preflight):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_preflight], hooks=[], configs=[],
        )
        ffmpeg = next(
            t for t in result.dependencies.cli_tools if t.name == "ffmpeg"
        )
        assert ffmpeg.install_hint == "apt install ffmpeg"
        assert ffmpeg.version_hint == ">=5.0"

    def test_preflight_env_vars_detected(self, skill_dir_with_preflight):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_preflight], hooks=[], configs=[],
        )
        env_names = {e.name for e in result.dependencies.env_vars}
        assert "OPENAI_API_KEY" in env_names
        assert "HF_TOKEN" in env_names

    def test_preflight_packages_detected(self, skill_dir_with_preflight):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_preflight], hooks=[], configs=[],
        )
        pkg_names = {p.name for p in result.dependencies.python_packages}
        assert "torch" in pkg_names
        assert "numpy" in pkg_names

    def test_script_and_preflight_merge(self, skill_dir_with_preflight):
        """Both the script scanner (main.sh -> git) and .preflight.yml (ffmpeg)
        results should appear in the same manifest."""
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_preflight], hooks=[], configs=[],
        )
        cli_names = {t.name for t in result.dependencies.cli_tools}
        assert "git" in cli_names   # from main.sh
        assert "ffmpeg" in cli_names  # from .preflight.yml

    def test_skill_tree_includes_system_deps(self, skill_dir_with_preflight):
        result = collect_inventory(
            agents=[], skills=[skill_dir_with_preflight], hooks=[], configs=[],
        )
        tree = next(
            t for t in result.dependencies.skill_trees
            if t.name == "preflight-skill"
        )
        assert "ffmpeg" in tree.system_deps
        assert "sox" in tree.system_deps


# ---------------------------------------------------------------------------
# 5. write_manifest() + read_manifest() round-trip
# ---------------------------------------------------------------------------


class TestManifestRoundTrip:
    """Serialization and deserialization preserves all manifest data."""

    def test_round_trip_preserves_metadata(self, tmp_path, manifest_with_data):
        path = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, path)
        loaded = read_manifest(path)

        assert loaded.manifest_version == manifest_with_data.manifest_version
        assert loaded.created_at == manifest_with_data.created_at
        assert loaded.source_platform == manifest_with_data.source_platform
        assert loaded.source_os == manifest_with_data.source_os
        assert loaded.source_arch == manifest_with_data.source_arch
        assert loaded.source_home == manifest_with_data.source_home

    def test_round_trip_preserves_contents(self, tmp_path, manifest_with_data):
        path = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, path)
        loaded = read_manifest(path)

        assert loaded.contents.agents == manifest_with_data.contents.agents
        assert loaded.contents.skills == manifest_with_data.contents.skills
        assert loaded.contents.hooks == manifest_with_data.contents.hooks
        assert loaded.contents.configs == manifest_with_data.contents.configs

    def test_round_trip_preserves_mcp_servers(self, tmp_path, manifest_with_data):
        path = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, path)
        loaded = read_manifest(path)

        assert len(loaded.dependencies.mcp_servers) == 1
        srv = loaded.dependencies.mcp_servers[0]
        assert srv.id == "graphiti"
        assert srv.install_type == "git-repo-python-venv"
        assert srv.repo_url == "https://github.com/example/graphiti.git"
        assert srv.runtime == "python"
        assert srv.auth_required is True
        assert srv.env_vars == ["GRAPHITI_TOKEN"]
        assert srv.required_by == ["agent-a"]

    def test_round_trip_preserves_cli_tools(self, tmp_path, manifest_with_data):
        path = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, path)
        loaded = read_manifest(path)

        cli_names = {t.name for t in loaded.dependencies.cli_tools}
        assert cli_names == {"jq", "curl"}

        jq_dep = next(t for t in loaded.dependencies.cli_tools if t.name == "jq")
        assert jq_dep.version_hint == ">=1.6"
        assert jq_dep.install_hint == "apt install jq"

    def test_round_trip_preserves_env_vars(self, tmp_path, manifest_with_data):
        path = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, path)
        loaded = read_manifest(path)

        assert len(loaded.dependencies.env_vars) == 1
        ev = loaded.dependencies.env_vars[0]
        assert ev.name == "MY_SECRET"
        assert ev.description == "A test secret"
        assert ev.critical is True

    def test_round_trip_preserves_python_packages(self, tmp_path, manifest_with_data):
        path = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, path)
        loaded = read_manifest(path)

        assert len(loaded.dependencies.python_packages) == 1
        pkg = loaded.dependencies.python_packages[0]
        assert pkg.name == "requests"
        assert pkg.ecosystem == "python"

    def test_round_trip_preserves_skill_trees(self, tmp_path, manifest_with_data):
        path = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, path)
        loaded = read_manifest(path)

        assert len(loaded.dependencies.skill_trees) == 1
        tree = loaded.dependencies.skill_trees[0]
        assert tree.name == "skill-one"
        assert tree.system_deps == ["jq"]

    def test_written_file_is_valid_json(self, tmp_path, manifest_with_data):
        path = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, path)
        data = json.loads(path.read_text())
        assert isinstance(data, dict)
        assert "manifest_version" in data

    def test_round_trip_via_asdict_equality(self, tmp_path, manifest_with_data):
        """The full dict representation should match after round-trip."""
        path = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, path)
        loaded = read_manifest(path)
        assert asdict(loaded) == asdict(manifest_with_data)

    def test_read_manifest_raises_on_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json at all")
        with pytest.raises(ValueError, match="Invalid manifest"):
            read_manifest(bad)

    def test_read_manifest_raises_on_non_object(self, tmp_path):
        bad = tmp_path / "array.json"
        bad.write_text("[1, 2, 3]")
        with pytest.raises(ValueError, match="not a JSON object"):
            read_manifest(bad)

    def test_write_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c" / "manifest.json"
        manifest = TransferManifest()
        write_manifest(manifest, nested)
        assert nested.is_file()


# ---------------------------------------------------------------------------
# 6. read_manifest_from_archive() with valid archive
# ---------------------------------------------------------------------------


class TestReadManifestFromArchive:
    """Reading manifest.json out of a tar.gz archive."""

    def test_reads_manifest_from_root(self, tmp_path, manifest_with_data):
        """manifest.json placed at archive root."""
        manifest_json = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, manifest_json)

        archive_path = tmp_path / "export.tar.gz"
        with tarfile.open(str(archive_path), "w:gz") as tf:
            tf.add(str(manifest_json), arcname="manifest.json")

        loaded = read_manifest_from_archive(archive_path)
        assert loaded is not None
        assert loaded.manifest_version == "2.0"
        assert loaded.source_os == "linux"

    def test_reads_manifest_from_nested_path(self, tmp_path, manifest_with_data):
        """manifest.json nested inside a subdirectory in the archive."""
        manifest_json = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, manifest_json)

        archive_path = tmp_path / "export.tar.gz"
        with tarfile.open(str(archive_path), "w:gz") as tf:
            tf.add(str(manifest_json), arcname="export/manifest.json")

        loaded = read_manifest_from_archive(archive_path)
        assert loaded is not None
        assert loaded.source_platform == "claude-code"

    def test_preserves_dependency_data(self, tmp_path, manifest_with_data):
        manifest_json = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, manifest_json)

        archive_path = tmp_path / "export.tar.gz"
        with tarfile.open(str(archive_path), "w:gz") as tf:
            tf.add(str(manifest_json), arcname="manifest.json")

        loaded = read_manifest_from_archive(archive_path)
        assert loaded is not None
        assert len(loaded.dependencies.mcp_servers) == 1
        assert loaded.dependencies.mcp_servers[0].id == "graphiti"

    def test_preserves_contents(self, tmp_path, manifest_with_data):
        manifest_json = tmp_path / "manifest.json"
        write_manifest(manifest_with_data, manifest_json)

        archive_path = tmp_path / "export.tar.gz"
        with tarfile.open(str(archive_path), "w:gz") as tf:
            tf.add(str(manifest_json), arcname="manifest.json")

        loaded = read_manifest_from_archive(archive_path)
        assert loaded is not None
        assert loaded.contents.agents == ["agent-a.md", "agent-b.md"]


# ---------------------------------------------------------------------------
# 7. read_manifest_from_archive() with legacy archive (no manifest)
# ---------------------------------------------------------------------------


class TestReadManifestFromLegacyArchive:
    """Archives that do not contain manifest.json should return None."""

    def test_returns_none_for_no_manifest(self, tmp_path):
        """Archive has files but no manifest.json."""
        some_file = tmp_path / "agents.md"
        some_file.write_text("# Some agent\n")

        archive_path = tmp_path / "legacy.tar.gz"
        with tarfile.open(str(archive_path), "w:gz") as tf:
            tf.add(str(some_file), arcname="agents.md")

        result = read_manifest_from_archive(archive_path)
        assert result is None

    def test_returns_none_for_empty_archive(self, tmp_path):
        archive_path = tmp_path / "empty.tar.gz"
        with tarfile.open(str(archive_path), "w:gz"):
            pass  # empty archive

        result = read_manifest_from_archive(archive_path)
        assert result is None

    def test_returns_none_for_corrupted_file(self, tmp_path):
        bad_file = tmp_path / "corrupted.tar.gz"
        bad_file.write_bytes(b"this is not a tar file at all")

        result = read_manifest_from_archive(bad_file)
        assert result is None

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        missing = tmp_path / "does-not-exist.tar.gz"
        result = read_manifest_from_archive(missing)
        assert result is None

    def test_returns_none_for_invalid_json_in_manifest(self, tmp_path):
        """Archive has a manifest.json but with broken JSON content."""
        bad_json = tmp_path / "manifest.json"
        bad_json.write_text("{broken json here!!!")

        archive_path = tmp_path / "bad-json.tar.gz"
        with tarfile.open(str(archive_path), "w:gz") as tf:
            tf.add(str(bad_json), arcname="manifest.json")

        result = read_manifest_from_archive(archive_path)
        assert result is None


# ---------------------------------------------------------------------------
# 8. deduplicate_dependencies() merges duplicate entries
# ---------------------------------------------------------------------------


class TestDeduplicateDependencies:
    """Deduplication merges entries by identity key and unifies required_by."""

    def test_merges_duplicate_mcp_servers(self):
        graph = DependencyGraph(
            mcp_servers=[
                McpServerDep(id="graphiti", install_type="unknown", required_by=["agent-a"]),
                McpServerDep(
                    id="graphiti",
                    install_type="git-repo-python-venv",
                    repo_url="https://github.com/example/graphiti.git",
                    required_by=["config"],
                ),
            ],
        )
        result = deduplicate_dependencies(graph)
        assert len(result.mcp_servers) == 1
        srv = result.mcp_servers[0]
        assert srv.id == "graphiti"
        assert "agent-a" in srv.required_by
        assert "config" in srv.required_by
        # The non-unknown install_type should win
        assert srv.install_type == "git-repo-python-venv"
        assert srv.repo_url == "https://github.com/example/graphiti.git"

    def test_merges_duplicate_cli_tools(self):
        graph = DependencyGraph(
            cli_tools=[
                CliToolDep(name="jq", version_hint=">=1.6", required_by=["skill-a"]),
                CliToolDep(name="jq", required_by=["skill-b"]),
                CliToolDep(name="curl", required_by=["skill-a"]),
            ],
        )
        result = deduplicate_dependencies(graph)
        assert len(result.cli_tools) == 2

        jq = next(t for t in result.cli_tools if t.name == "jq")
        assert "skill-a" in jq.required_by
        assert "skill-b" in jq.required_by
        assert jq.version_hint == ">=1.6"

    def test_merges_duplicate_env_vars(self):
        graph = DependencyGraph(
            env_vars=[
                EnvVarDep(name="API_KEY", description="The key", critical=False, required_by=["a"]),
                EnvVarDep(name="API_KEY", critical=True, required_by=["b"]),
            ],
        )
        result = deduplicate_dependencies(graph)
        assert len(result.env_vars) == 1
        ev = result.env_vars[0]
        assert ev.name == "API_KEY"
        assert ev.description == "The key"
        assert ev.critical is True
        assert "a" in ev.required_by
        assert "b" in ev.required_by

    def test_merges_duplicate_python_packages(self):
        graph = DependencyGraph(
            python_packages=[
                PackageDep(name="requests", ecosystem="python", required_by=["x"]),
                PackageDep(name="requests", ecosystem="python", required_by=["y"]),
            ],
        )
        result = deduplicate_dependencies(graph)
        assert len(result.python_packages) == 1
        pkg = result.python_packages[0]
        assert "x" in pkg.required_by
        assert "y" in pkg.required_by

    def test_preserves_unique_entries(self):
        graph = DependencyGraph(
            cli_tools=[
                CliToolDep(name="jq", required_by=["a"]),
                CliToolDep(name="curl", required_by=["b"]),
                CliToolDep(name="wget", required_by=["c"]),
            ],
        )
        result = deduplicate_dependencies(graph)
        names = sorted(t.name for t in result.cli_tools)
        assert names == ["curl", "jq", "wget"]

    def test_docker_deps_kept_as_is(self):
        from agent_transfer.utils.preflight.manifest import DockerDep

        graph = DependencyGraph(
            docker=[
                DockerDep(type="image", image="redis:7", required_by=["a"]),
                DockerDep(type="image", image="redis:7", required_by=["b"]),
            ],
        )
        result = deduplicate_dependencies(graph)
        # Docker deps have no natural dedup key, so both remain
        assert len(result.docker) == 2

    def test_empty_graph_returns_empty(self):
        graph = DependencyGraph()
        result = deduplicate_dependencies(graph)
        assert result.mcp_servers == []
        assert result.cli_tools == []
        assert result.env_vars == []
        assert result.python_packages == []

    def test_mcp_server_auth_required_propagates(self):
        """If either copy has auth_required=True, the merged result should too."""
        graph = DependencyGraph(
            mcp_servers=[
                McpServerDep(id="srv", auth_required=False, required_by=["a"]),
                McpServerDep(id="srv", auth_required=True, required_by=["b"]),
            ],
        )
        result = deduplicate_dependencies(graph)
        assert result.mcp_servers[0].auth_required is True

    def test_mcp_server_env_vars_merged(self):
        graph = DependencyGraph(
            mcp_servers=[
                McpServerDep(id="srv", env_vars=["TOKEN_A"], required_by=["a"]),
                McpServerDep(id="srv", env_vars=["TOKEN_B"], required_by=["b"]),
            ],
        )
        result = deduplicate_dependencies(graph)
        assert sorted(result.mcp_servers[0].env_vars) == ["TOKEN_A", "TOKEN_B"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestCollectInventoryEdgeCases:
    """Additional edge-case coverage."""

    def test_agent_with_no_mcp_references(self, tmp_path):
        """An agent file with no mcp__ patterns produces no MCP deps."""
        md = tmp_path / "plain.md"
        md.write_text("# Just a plain agent\nNo tools here.\n")
        result = collect_inventory(
            agents=[md], skills=[], hooks=[], configs=[],
        )
        assert result.dependencies.mcp_servers == []
        assert "plain.md" in result.contents.agents

    def test_skill_dir_is_actually_a_file_skipped(self, tmp_path):
        """If a skill path points to a file instead of a directory, skip it."""
        not_a_dir = tmp_path / "oops.txt"
        not_a_dir.write_text("I am a file")
        result = collect_inventory(
            agents=[], skills=[not_a_dir], hooks=[], configs=[],
        )
        assert result.contents.skills == []

    def test_collect_then_deduplicate_idempotent(self, agent_md_with_mcp):
        """Running deduplicate on already-unique output should not change it."""
        manifest = collect_inventory(
            agents=[agent_md_with_mcp],
            skills=[], hooks=[], configs=[],
        )
        deduped = deduplicate_dependencies(manifest.dependencies)
        original_ids = sorted(s.id for s in manifest.dependencies.mcp_servers)
        deduped_ids = sorted(s.id for s in deduped.mcp_servers)
        assert original_ids == deduped_ids
