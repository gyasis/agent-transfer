"""Comprehensive unit tests for all 6 preflight scanners.

Tests cover happy paths, edge cases, error handling, and R8 compliance
(env var values are never captured).

Python >= 3.8 compatible. Only requires pytest (no external test deps).
"""

import struct
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 1. MCP Scanner
# ---------------------------------------------------------------------------
from agent_transfer.utils.preflight.scanners.mcp_scanner import (
    extract_mcp_server_ids,
    scan_mcp_servers,
)


class TestExtractMcpServerIds:
    """Tests for extract_mcp_server_ids()."""

    def test_single_tool_declaration(self):
        content = "mcp__github__create_issue"
        result = extract_mcp_server_ids(content)
        assert result == ["github"]

    def test_multiple_unique_servers(self):
        content = (
            "mcp__github__create_issue\n"
            "mcp__slack__send_message\n"
            "mcp__github__list_repos\n"
        )
        result = extract_mcp_server_ids(content)
        assert result == ["github", "slack"]

    def test_deduplication(self):
        content = "mcp__foo__bar mcp__foo__baz mcp__foo__qux"
        result = extract_mcp_server_ids(content)
        assert result == ["foo"]

    def test_sorted_output(self):
        content = "mcp__zebra__tool mcp__alpha__tool mcp__middle__tool"
        result = extract_mcp_server_ids(content)
        assert result == ["alpha", "middle", "zebra"]

    def test_empty_string(self):
        assert extract_mcp_server_ids("") == []

    def test_no_matches(self):
        content = "This is regular markdown with no tool declarations."
        assert extract_mcp_server_ids(content) == []

    def test_hyphenated_server_id(self):
        content = "mcp__my-server__tool_name"
        result = extract_mcp_server_ids(content)
        assert result == ["my-server"]

    def test_partial_pattern_no_match(self):
        # Missing the tool part after second __
        content = "mcp__serveronly"
        assert extract_mcp_server_ids(content) == []


class TestScanMcpServers:
    """Tests for scan_mcp_servers()."""

    def test_npx_server(self):
        config = {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_TOKEN": "ghp_secret123"},
                }
            }
        }
        result = scan_mcp_servers(config, required_by="agent.md")
        assert len(result) == 1
        dep = result[0]
        assert dep.id == "github"
        assert dep.install_type == "npm-on-demand"
        assert dep.package == "@modelcontextprotocol/server-github"
        assert dep.runtime == "node"
        assert dep.auth_required is True
        assert dep.env_vars == ["GITHUB_TOKEN"]
        assert dep.required_by == ["agent.md"]

    def test_bunx_server(self):
        config = {
            "mcpServers": {
                "myserver": {
                    "command": "bunx",
                    "args": ["some-mcp-package"],
                }
            }
        }
        result = scan_mcp_servers(config)
        assert len(result) == 1
        dep = result[0]
        assert dep.install_type == "bun-on-demand"
        assert dep.package == "some-mcp-package"
        assert dep.runtime == "node"

    def test_python_server(self):
        config = {
            "mcpServers": {
                "pyserver": {
                    "command": "python",
                    "args": ["-m", "my_mcp_server"],
                }
            }
        }
        result = scan_mcp_servers(config)
        dep = result[0]
        assert dep.install_type == "git-repo-python-venv"
        assert dep.runtime == "python"

    def test_uv_server(self):
        config = {
            "mcpServers": {
                "uvserver": {
                    "command": "uv",
                    "args": ["run", "my_server.py"],
                }
            }
        }
        result = scan_mcp_servers(config)
        dep = result[0]
        assert dep.install_type == "git-repo-uv"
        assert dep.runtime == "python"

    def test_remote_sse_server(self):
        config = {
            "mcpServers": {
                "remote": {
                    "url": "https://example.com/mcp/sse",
                }
            }
        }
        result = scan_mcp_servers(config)
        dep = result[0]
        assert dep.install_type == "remote-sse"
        assert dep.runtime == "remote"
        assert dep.endpoint == "https://example.com/mcp/sse"

    def test_docker_server(self):
        config = {
            "mcpServers": {
                "dkr": {
                    "command": "docker",
                    "args": ["run", "--rm", "myimage:latest"],
                }
            }
        }
        result = scan_mcp_servers(config)
        dep = result[0]
        assert dep.install_type == "docker"
        assert dep.runtime == "docker"

    def test_flat_server_dict(self):
        """Accepts a flat dict without the mcpServers wrapper."""
        config = {
            "myserver": {
                "command": "npx",
                "args": ["-y", "some-pkg"],
            }
        }
        result = scan_mcp_servers(config)
        assert len(result) == 1
        assert result[0].id == "myserver"

    def test_empty_config(self):
        assert scan_mcp_servers({}) == []

    def test_env_vars_names_only_r8(self):
        """R8 compliance: only env var NAMES are captured, never values."""
        config = {
            "mcpServers": {
                "s": {
                    "command": "npx",
                    "args": ["pkg"],
                    "env": {
                        "API_KEY": "supersecret123",
                        "DB_HOST": "prod.db.example.com",
                    },
                }
            }
        }
        result = scan_mcp_servers(config)
        dep = result[0]
        # Only names, sorted
        assert dep.env_vars == ["API_KEY", "DB_HOST"]
        # Values must NOT appear anywhere in the dep
        assert "supersecret123" not in str(dep)
        assert "prod.db.example.com" not in str(dep)

    def test_auth_detection_patterns(self):
        """Auth is detected from KEY, TOKEN, SECRET, AUTH in env var names."""
        config = {
            "mcpServers": {
                "a": {"command": "npx", "args": ["x"], "env": {"MY_SECRET": "v"}},
            }
        }
        dep = scan_mcp_servers(config)[0]
        assert dep.auth_required is True

    def test_no_auth_when_no_secret_vars(self):
        config = {
            "mcpServers": {
                "a": {"command": "npx", "args": ["x"], "env": {"LOG_LEVEL": "debug"}},
            }
        }
        dep = scan_mcp_servers(config)[0]
        assert dep.auth_required is False

    def test_no_env_section(self):
        config = {
            "mcpServers": {
                "a": {"command": "npx", "args": ["pkg"]},
            }
        }
        dep = scan_mcp_servers(config)[0]
        assert dep.env_vars == []
        assert dep.auth_required is False

    def test_required_by_empty_when_not_provided(self):
        config = {"mcpServers": {"a": {"command": "npx", "args": ["x"]}}}
        dep = scan_mcp_servers(config)[0]
        assert dep.required_by == []

    def test_multiple_servers(self):
        config = {
            "mcpServers": {
                "alpha": {"command": "npx", "args": ["a"]},
                "beta": {"command": "python", "args": ["b.py"]},
            }
        }
        result = scan_mcp_servers(config, required_by="test")
        assert len(result) == 2
        ids = {d.id for d in result}
        assert ids == {"alpha", "beta"}

    def test_unknown_command(self):
        config = {
            "mcpServers": {
                "mystery": {"command": "/opt/custom/bin/server"},
            }
        }
        dep = scan_mcp_servers(config)[0]
        assert dep.install_type == "unknown"


# ---------------------------------------------------------------------------
# 2. Script Scanner
# ---------------------------------------------------------------------------
from agent_transfer.utils.preflight.scanners.script_scanner import (
    scan_script_file,
    scan_scripts,
)


class TestScanScriptFile:
    """Tests for scan_script_file()."""

    def test_shell_cli_tools(self, tmp_path):
        script = tmp_path / "setup.sh"
        script.write_text(
            "#!/bin/bash\n"
            "git clone https://example.com/repo.git\n"
            "npm install\n"
            "docker build .\n"
        )
        result = scan_script_file(script, required_by="hook")
        names = [d.name for d in result["cli_tools"]]
        assert "git" in names
        assert "npm" in names
        assert "docker" in names

    def test_shell_which_detection(self, tmp_path):
        script = tmp_path / "check.sh"
        script.write_text("which jq || echo 'missing'\n")
        result = scan_script_file(script)
        names = [d.name for d in result["cli_tools"]]
        assert "jq" in names

    def test_shell_command_v_detection(self, tmp_path):
        script = tmp_path / "check.sh"
        script.write_text("command -v curl\n")
        result = scan_script_file(script)
        names = [d.name for d in result["cli_tools"]]
        assert "curl" in names

    def test_shell_subshell_detection(self, tmp_path):
        script = tmp_path / "run.sh"
        script.write_text("result=$(git log --oneline)\n")
        result = scan_script_file(script)
        names = [d.name for d in result["cli_tools"]]
        assert "git" in names

    def test_shell_pipe_detection(self, tmp_path):
        script = tmp_path / "run.sh"
        script.write_text("cat file.json | jq '.key'\n")
        result = scan_script_file(script)
        names = [d.name for d in result["cli_tools"]]
        assert "jq" in names

    def test_shell_env_vars(self, tmp_path):
        script = tmp_path / "run.sh"
        script.write_text(
            "#!/bin/bash\n"
            "echo $HOME\n"
            "echo ${API_KEY}\n"
            "echo $CUSTOM_VAR\n"
        )
        result = scan_script_file(script)
        names = [d.name for d in result["env_vars"]]
        assert "HOME" in names
        assert "API_KEY" in names
        assert "CUSTOM_VAR" in names

    def test_shell_env_vars_skip_internals(self, tmp_path):
        script = tmp_path / "run.sh"
        script.write_text(
            "echo $1 $2 $? $# $@ $*\n"
            "echo $BASH_VERSION $RANDOM $SHLVL\n"
        )
        result = scan_script_file(script)
        names = [d.name for d in result["env_vars"]]
        # None of these should appear
        for internal in ["1", "2", "?", "#", "BASH_VERSION", "RANDOM", "SHLVL"]:
            assert internal not in names

    def test_shell_source_detection(self, tmp_path):
        script = tmp_path / "run.sh"
        script.write_text(
            "source /etc/profile\n"
            ". ./helpers.sh\n"
        )
        result = scan_script_file(script)
        paths = [d.path for d in result["sourced_files"]]
        assert "/etc/profile" in paths
        assert "./helpers.sh" in paths

    def test_python_env_vars(self, tmp_path):
        script = tmp_path / "app.py"
        script.write_text(
            "import os\n"
            "key = os.environ['API_KEY']\n"
            "host = os.environ.get('DB_HOST')\n"
            "port = os.getenv('DB_PORT')\n"
        )
        result = scan_script_file(script)
        names = [d.name for d in result["env_vars"]]
        assert "API_KEY" in names
        assert "DB_HOST" in names
        assert "DB_PORT" in names

    def test_python_imports(self, tmp_path):
        script = tmp_path / "app.py"
        script.write_text(
            "import requests\n"
            "from flask import Flask\n"
            "import os\n"
            "import json\n"
            "from pathlib import Path\n"
        )
        result = scan_script_file(script)
        pkg_names = [d.name for d in result["packages"]]
        # Third-party should appear
        assert "requests" in pkg_names
        assert "flask" in pkg_names
        # Stdlib should NOT appear
        assert "os" not in pkg_names
        assert "json" not in pkg_names
        assert "pathlib" not in pkg_names

    def test_python_imports_ecosystem(self, tmp_path):
        script = tmp_path / "app.py"
        script.write_text("import requests\n")
        result = scan_script_file(script)
        assert result["packages"][0].ecosystem == "python"

    def test_js_env_vars(self, tmp_path):
        script = tmp_path / "app.js"
        script.write_text(
            "const key = process.env.API_KEY;\n"
            "const host = process.env.DB_HOST;\n"
        )
        result = scan_script_file(script)
        names = [d.name for d in result["env_vars"]]
        assert "API_KEY" in names
        assert "DB_HOST" in names

    def test_js_require_packages(self, tmp_path):
        script = tmp_path / "app.js"
        script.write_text(
            'const express = require("express");\n'
            "const helper = require('./helper');\n"
            'const scoped = require("@scope/pkg");\n'
        )
        result = scan_script_file(script)
        pkg_names = [d.name for d in result["packages"]]
        assert "express" in pkg_names
        assert "@scope/pkg" in pkg_names
        # Relative requires go to sourced_files
        sourced = [d.path for d in result["sourced_files"]]
        assert "./helper" in sourced

    def test_js_packages_ecosystem(self, tmp_path):
        script = tmp_path / "app.js"
        script.write_text('const x = require("express");\n')
        result = scan_script_file(script)
        assert result["packages"][0].ecosystem == "node"

    def test_unsupported_extension(self, tmp_path):
        script = tmp_path / "config.toml"
        script.write_text("[section]\nkey = value\n")
        result = scan_script_file(script)
        assert result == {
            "cli_tools": [],
            "env_vars": [],
            "sourced_files": [],
            "packages": [],
        }

    def test_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.sh"
        result = scan_script_file(missing)
        assert result["cli_tools"] == []
        assert result["env_vars"] == []

    def test_empty_file(self, tmp_path):
        script = tmp_path / "empty.sh"
        script.write_text("")
        result = scan_script_file(script)
        assert all(len(v) == 0 for v in result.values())

    def test_required_by_propagated(self, tmp_path):
        script = tmp_path / "run.sh"
        script.write_text("git status\n")
        result = scan_script_file(script, required_by="my-hook")
        assert result["cli_tools"][0].required_by == ["my-hook"]

    def test_required_by_empty(self, tmp_path):
        script = tmp_path / "run.sh"
        script.write_text("git status\n")
        result = scan_script_file(script)
        assert result["cli_tools"][0].required_by == []

    def test_env_var_values_never_captured_r8(self, tmp_path):
        """R8 compliance: values must not appear in results."""
        script = tmp_path / "run.sh"
        script.write_text(
            'export MY_SECRET="super_secret_value_12345"\n'
            "curl -H $MY_SECRET https://api.example.com\n"
        )
        result = scan_script_file(script)
        full_str = str(result)
        assert "super_secret_value_12345" not in full_str


class TestScanScripts:
    """Tests for scan_scripts() multi-file merging."""

    def test_merge_deduplicates(self, tmp_path):
        s1 = tmp_path / "a.sh"
        s1.write_text("git clone x\ncurl http://example.com\n")
        s2 = tmp_path / "b.sh"
        s2.write_text("git push\nnpm install\n")

        result = scan_scripts([s1, s2], required_by="test")
        cli_names = [d.name for d in result["cli_tools"]]
        # git appears in both files but should only be listed once
        assert cli_names.count("git") == 1
        assert "curl" in cli_names
        assert "npm" in cli_names

    def test_empty_file_list(self):
        result = scan_scripts([])
        assert all(len(v) == 0 for v in result.values())

    def test_merge_env_vars_deduplicated(self, tmp_path):
        s1 = tmp_path / "a.sh"
        s1.write_text("echo $HOME\necho $API_KEY\n")
        s2 = tmp_path / "b.sh"
        s2.write_text("echo $HOME\necho $DB_HOST\n")

        result = scan_scripts([s1, s2])
        env_names = [d.name for d in result["env_vars"]]
        assert env_names.count("HOME") == 1
        assert "API_KEY" in env_names
        assert "DB_HOST" in env_names

    def test_results_sorted(self, tmp_path):
        s1 = tmp_path / "a.sh"
        s1.write_text("npm install\ngit status\ncurl http://x\n")
        result = scan_scripts([s1])
        cli_names = [d.name for d in result["cli_tools"]]
        assert cli_names == sorted(cli_names)


# ---------------------------------------------------------------------------
# 3. Binary Scanner
# ---------------------------------------------------------------------------
from agent_transfer.utils.preflight.scanners.binary_scanner import (
    is_elf_binary,
    scan_binary,
)


def _make_elf_binary(
    path,
    arch=0x3E,  # x86_64
    os_abi=0x00,  # linux
    extra_content=b"",
):
    """Create a minimal ELF binary file for testing."""
    # ELF header: magic(4) + class(1) + data(1) + version(1) + osabi(1)
    # + padding(8) + type(2) + machine(2) = 20 bytes minimum
    header = bytearray(20)
    header[0:4] = b"\x7fELF"  # magic
    header[4] = 2  # 64-bit
    header[5] = 1  # little-endian
    header[6] = 1  # ELF version
    header[7] = os_abi
    # bytes 8-15: padding (zeros)
    # bytes 16-17: type (ET_EXEC = 2)
    struct.pack_into("<H", header, 16, 2)
    # bytes 18-19: machine
    struct.pack_into("<H", header, 18, arch)

    path.write_bytes(bytes(header) + extra_content)
    return path


class TestIsElfBinary:
    """Tests for is_elf_binary()."""

    def test_valid_elf(self, tmp_path):
        binary = _make_elf_binary(tmp_path / "test_bin")
        assert is_elf_binary(binary) is True

    def test_not_elf_text_file(self, tmp_path):
        txt = tmp_path / "not_elf.txt"
        txt.write_text("Hello world")
        assert is_elf_binary(txt) is False

    def test_not_elf_short_file(self, tmp_path):
        short = tmp_path / "short"
        short.write_bytes(b"\x7fEL")  # only 3 bytes
        assert is_elf_binary(short) is False

    def test_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent"
        assert is_elf_binary(missing) is False

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty"
        empty.write_bytes(b"")
        assert is_elf_binary(empty) is False

    def test_wrong_magic(self, tmp_path):
        f = tmp_path / "wrong"
        f.write_bytes(b"\x7fXYZ" + b"\x00" * 16)
        assert is_elf_binary(f) is False


class TestScanBinary:
    """Tests for scan_binary()."""

    def test_x86_64_linux(self, tmp_path):
        binary = _make_elf_binary(tmp_path / "mybin", arch=0x3E, os_abi=0x00)
        dep = scan_binary(binary, required_by="skill")
        assert dep is not None
        assert dep.name == "mybin"
        assert dep.arch == "x86_64"
        assert dep.os == "linux"
        assert dep.path == str(binary)
        assert dep.required_by == ["skill"]

    def test_aarch64(self, tmp_path):
        binary = _make_elf_binary(tmp_path / "arm_bin", arch=0xB7, os_abi=0x03)
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.arch == "aarch64"
        assert dep.os == "linux"

    def test_x86_32(self, tmp_path):
        binary = _make_elf_binary(tmp_path / "x86", arch=0x03)
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.arch == "x86"

    def test_arm32(self, tmp_path):
        binary = _make_elf_binary(tmp_path / "arm32", arch=0x28)
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.arch == "arm"

    def test_unknown_arch(self, tmp_path):
        binary = _make_elf_binary(tmp_path / "weird", arch=0xFF)
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.arch == "unknown"

    def test_unknown_osabi(self, tmp_path):
        binary = _make_elf_binary(tmp_path / "weird_os", os_abi=0xFF)
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.os == "unknown"

    def test_non_elf_returns_none(self, tmp_path):
        txt = tmp_path / "notelf"
        txt.write_text("not a binary")
        assert scan_binary(txt) is None

    def test_missing_file_returns_none(self, tmp_path):
        missing = tmp_path / "gone"
        assert scan_binary(missing) is None

    def test_rust_language_detection(self, tmp_path):
        binary = _make_elf_binary(
            tmp_path / "rustbin",
            extra_content=b"\x00" * 100 + b".rustc" + b"\x00" * 100,
        )
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.source_lang == "rust"

    def test_go_language_detection(self, tmp_path):
        binary = _make_elf_binary(
            tmp_path / "gobin",
            extra_content=b"\x00" * 100 + b"go.buildid" + b"\x00" * 100,
        )
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.source_lang == "go"

    def test_unknown_language(self, tmp_path):
        binary = _make_elf_binary(tmp_path / "cbin")
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.source_lang is None

    def test_build_command_cargo(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        (project / "Cargo.toml").write_text("[package]\nname = 'test'\n")
        (project / "target" / "release").mkdir(parents=True, exist_ok=True)
        binary = _make_elf_binary(project / "target" / "release" / "mybin")
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.build_command == "cargo build --release"

    def test_build_command_makefile(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "Makefile").write_text("all:\n\tgcc main.c\n")
        binary = _make_elf_binary(project / "mybin")
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.build_command == "make"

    def test_no_build_command(self, tmp_path):
        binary = _make_elf_binary(tmp_path / "standalone")
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.build_command is None

    def test_required_by_empty(self, tmp_path):
        binary = _make_elf_binary(tmp_path / "b")
        dep = scan_binary(binary)
        assert dep is not None
        assert dep.required_by == []

    def test_truncated_elf_header(self, tmp_path):
        """ELF magic is valid but header is too short for metadata."""
        f = tmp_path / "truncated"
        f.write_bytes(b"\x7fELF" + b"\x00" * 5)  # Only 9 bytes, need 20
        assert scan_binary(f) is None


# ---------------------------------------------------------------------------
# 4. Git Scanner
# ---------------------------------------------------------------------------
from agent_transfer.utils.preflight.scanners.git_scanner import (
    detect_setup_method,
    extract_git_remote,
    scan_git_repo,
)


def _make_git_repo(repo_path, remote_url="https://github.com/user/repo.git"):
    """Create a fake .git/config with a remote origin."""
    git_dir = repo_path / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    config = git_dir / "config"
    config.write_text(
        '[core]\n'
        '\trepositoryformatversion = 0\n'
        '[remote "origin"]\n'
        f'\turl = {remote_url}\n'
        '\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
    )
    return git_dir


class TestExtractGitRemote:
    """Tests for extract_git_remote()."""

    def test_https_remote(self, tmp_path):
        git_dir = _make_git_repo(tmp_path / "repo", "https://github.com/user/repo.git")
        url = extract_git_remote(git_dir)
        assert url == "https://github.com/user/repo.git"

    def test_ssh_remote(self, tmp_path):
        git_dir = _make_git_repo(tmp_path / "repo", "git@github.com:user/repo.git")
        url = extract_git_remote(git_dir)
        assert url == "git@github.com:user/repo.git"

    def test_no_config_file(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        # No config file inside
        assert extract_git_remote(git_dir) is None

    def test_no_remote_section(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text("[core]\n\tbare = false\n")
        assert extract_git_remote(git_dir) is None

    def test_malformed_config(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text("this is not valid ini content {{{ [[[")
        assert extract_git_remote(git_dir) is None

    def test_nonexistent_git_dir(self, tmp_path):
        missing = tmp_path / ".git"
        assert extract_git_remote(missing) is None


class TestDetectSetupMethod:
    """Tests for detect_setup_method()."""

    def test_cargo(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\n')
        assert detect_setup_method(tmp_path) == "cargo"

    def test_uv_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[build-system]\nrequires = ['hatchling']\n"
            "[tool.uv]\ndev-dependencies = []\n"
        )
        assert detect_setup_method(tmp_path) == "uv"

    def test_python_venv_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[build-system]\nrequires = ['setuptools']\n"
        )
        assert detect_setup_method(tmp_path) == "python-venv"

    def test_npm(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "test"}')
        assert detect_setup_method(tmp_path) == "npm"

    def test_docker(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM python:3.11\n")
        assert detect_setup_method(tmp_path) == "docker"

    def test_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask\nrequests\n")
        assert detect_setup_method(tmp_path) == "pip"

    def test_fallback_pip(self, tmp_path):
        # Empty directory, no project files
        assert detect_setup_method(tmp_path) == "pip"

    def test_priority_cargo_over_npm(self, tmp_path):
        """Cargo.toml takes priority over package.json."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\n')
        (tmp_path / "package.json").write_text('{"name": "test"}')
        assert detect_setup_method(tmp_path) == "cargo"

    def test_priority_pyproject_over_npm(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        assert detect_setup_method(tmp_path) == "python-venv"


class TestScanGitRepo:
    """Tests for scan_git_repo()."""

    def test_valid_repo(self, tmp_path):
        repo = tmp_path / "myproject"
        repo.mkdir()
        _make_git_repo(repo, "https://github.com/user/myproject.git")
        (repo / "package.json").write_text('{"name": "myproject"}')

        dep = scan_git_repo(repo, required_by="skill")
        assert dep is not None
        assert dep.name == "myproject"
        assert dep.repo_url == "https://github.com/user/myproject.git"
        assert dep.local_path == str(repo)
        assert dep.setup_method == "npm"
        assert dep.required_by == ["skill"]

    def test_not_a_git_repo(self, tmp_path):
        plain_dir = tmp_path / "notagit"
        plain_dir.mkdir()
        assert scan_git_repo(plain_dir) is None

    def test_git_dir_no_remote(self, tmp_path):
        repo = tmp_path / "norepo"
        repo.mkdir()
        git_dir = repo / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]\n\tbare = false\n")
        assert scan_git_repo(repo) is None

    def test_required_by_empty(self, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        _make_git_repo(repo, "https://github.com/user/r.git")
        dep = scan_git_repo(repo)
        assert dep is not None
        assert dep.required_by == []

    def test_nonexistent_dir(self, tmp_path):
        missing = tmp_path / "missing"
        assert scan_git_repo(missing) is None


# ---------------------------------------------------------------------------
# 5. Docker Scanner
# ---------------------------------------------------------------------------
from agent_transfer.utils.preflight.scanners.docker_scanner import (
    scan_docker_in_scripts,
    scan_for_compose,
    scan_for_dockerfiles,
)


class TestScanForDockerfiles:
    """Tests for scan_for_dockerfiles()."""

    def test_standard_dockerfile(self, tmp_path):
        (tmp_path / "Dockerfile").write_text(
            "FROM python:3.11-slim\n"
            "COPY . /app\n"
            "RUN pip install -r requirements.txt\n"
        )
        deps = scan_for_dockerfiles(tmp_path, required_by="project")
        assert len(deps) == 1
        assert deps[0].type == "image"
        assert deps[0].image == "python:3.11-slim"
        assert deps[0].required_by == ["project"]

    def test_multistage_dockerfile(self, tmp_path):
        (tmp_path / "Dockerfile").write_text(
            "FROM node:18 AS builder\n"
            "RUN npm ci\n"
            "FROM nginx:alpine\n"
            "COPY --from=builder /app/dist /usr/share/nginx/html\n"
        )
        deps = scan_for_dockerfiles(tmp_path)
        images = [d.image for d in deps]
        assert "node:18" in images
        assert "nginx:alpine" in images

    def test_dockerfile_with_prefix(self, tmp_path):
        (tmp_path / "Dockerfile.dev").write_text("FROM python:3.11\n")
        deps = scan_for_dockerfiles(tmp_path)
        assert len(deps) == 1
        assert deps[0].image == "python:3.11"

    def test_dockerfile_with_suffix(self, tmp_path):
        (tmp_path / "app.dockerfile").write_text("FROM golang:1.21\n")
        deps = scan_for_dockerfiles(tmp_path)
        assert len(deps) == 1
        assert deps[0].image == "golang:1.21"

    def test_dockerfile_with_arg_variable(self, tmp_path):
        (tmp_path / "Dockerfile").write_text(
            "ARG BASE_IMAGE=python:3.11\n"
            "FROM $BASE_IMAGE\n"
        )
        deps = scan_for_dockerfiles(tmp_path)
        # $BASE_IMAGE should be skipped; file still recorded
        assert len(deps) == 1
        assert deps[0].image is None

    def test_dockerfile_platform_flag(self, tmp_path):
        (tmp_path / "Dockerfile").write_text(
            "FROM --platform=linux/amd64 python:3.11\n"
        )
        deps = scan_for_dockerfiles(tmp_path)
        assert len(deps) == 1
        assert deps[0].image == "python:3.11"

    def test_no_dockerfiles(self, tmp_path):
        (tmp_path / "README.md").write_text("Hello")
        deps = scan_for_dockerfiles(tmp_path)
        assert deps == []

    def test_nonexistent_directory(self, tmp_path):
        missing = tmp_path / "nope"
        deps = scan_for_dockerfiles(missing)
        assert deps == []

    def test_empty_dockerfile(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("# empty dockerfile\n")
        deps = scan_for_dockerfiles(tmp_path)
        # Should still record the file even with no FROM
        assert len(deps) == 1
        assert deps[0].image is None


class TestScanForCompose:
    """Tests for scan_for_compose()."""

    def test_compose_with_services(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text(
            "version: '3'\n"
            "services:\n"
            "  web:\n"
            "    image: nginx\n"
            "  db:\n"
            "    image: postgres:15\n"
        )
        deps = scan_for_compose(tmp_path, required_by="project")
        assert len(deps) == 1
        assert deps[0].type == "compose"
        assert sorted(deps[0].services) == ["db", "web"]
        assert deps[0].required_by == ["project"]

    def test_compose_yaml_extension(self, tmp_path):
        (tmp_path / "docker-compose.yaml").write_text(
            "services:\n  app:\n    build: .\n"
        )
        deps = scan_for_compose(tmp_path)
        assert len(deps) == 1
        assert deps[0].services == ["app"]

    def test_compose_short_name(self, tmp_path):
        (tmp_path / "compose.yml").write_text(
            "services:\n  api:\n    build: .\n"
        )
        deps = scan_for_compose(tmp_path)
        assert len(deps) == 1

    def test_malformed_yaml(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text(
            "not: valid: yaml: {{{\n"
        )
        deps = scan_for_compose(tmp_path)
        # Should still record the file, just no services parsed
        assert len(deps) == 1
        assert deps[0].services == []

    def test_no_compose_files(self, tmp_path):
        deps = scan_for_compose(tmp_path)
        assert deps == []

    def test_nonexistent_directory(self, tmp_path):
        missing = tmp_path / "nope"
        deps = scan_for_compose(missing)
        assert deps == []

    def test_compose_no_services_key(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
        deps = scan_for_compose(tmp_path)
        assert len(deps) == 1
        assert deps[0].services == []


class TestScanDockerInScripts:
    """Tests for scan_docker_in_scripts()."""

    def test_docker_run_simple(self):
        content = "docker run nginx:latest"
        deps = scan_docker_in_scripts(content, required_by="script.sh")
        assert len(deps) == 1
        assert deps[0].image == "nginx:latest"
        assert deps[0].required_by == ["script.sh"]

    def test_docker_run_with_flags(self):
        content = "docker run -d -p 8080:80 --name web nginx:alpine"
        deps = scan_docker_in_scripts(content)
        assert len(deps) == 1
        assert deps[0].image == "nginx:alpine"

    def test_docker_run_variable_image(self):
        content = "docker run $IMAGE_NAME"
        deps = scan_docker_in_scripts(content)
        assert len(deps) == 1
        # Variable references are rejected
        assert deps[0].image is None

    def test_multiple_docker_run(self):
        content = (
            "docker run redis:7\n"
            "docker run postgres:15\n"
        )
        deps = scan_docker_in_scripts(content)
        images = [d.image for d in deps]
        assert "redis:7" in images
        assert "postgres:15" in images

    def test_no_docker_run(self):
        content = "echo 'no docker here'\ngit status\n"
        deps = scan_docker_in_scripts(content)
        assert deps == []

    def test_empty_content(self):
        deps = scan_docker_in_scripts("")
        assert deps == []

    def test_required_by_empty(self):
        content = "docker run alpine"
        deps = scan_docker_in_scripts(content)
        assert deps[0].required_by == []


# ---------------------------------------------------------------------------
# 6. Preflight YAML Scanner
# ---------------------------------------------------------------------------
from agent_transfer.utils.preflight.scanners.preflight_yml import (
    PreflightConfig,
    read_preflight_yml,
)


class TestReadPreflightYml:
    """Tests for read_preflight_yml()."""

    def test_full_valid_config(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text(
            "dependencies:\n"
            "  cli_tools:\n"
            "    - name: terraform\n"
            "      install_hint: brew install terraform\n"
            "      version_hint: '>=1.5'\n"
            "    - name: kubectl\n"
            "  env_vars:\n"
            "    - name: AWS_ACCESS_KEY_ID\n"
            "      description: AWS access key\n"
            "    - name: AWS_SECRET_ACCESS_KEY\n"
            "  packages:\n"
            "    - name: boto3\n"
            "      ecosystem: python\n"
            "    - name: express\n"
            "      ecosystem: node\n"
            "notes:\n"
            "  - Remember to configure AWS credentials\n"
            "  - Run terraform init first\n"
        )
        config = read_preflight_yml(yml, required_by="my-skill")

        assert len(config.cli_tools) == 2
        assert config.cli_tools[0].name == "terraform"
        assert config.cli_tools[0].install_hint == "brew install terraform"
        assert config.cli_tools[0].version_hint == ">=1.5"
        assert config.cli_tools[0].required_by == ["my-skill"]
        assert config.cli_tools[1].name == "kubectl"

        assert len(config.env_vars) == 2
        assert config.env_vars[0].name == "AWS_ACCESS_KEY_ID"
        assert config.env_vars[0].description == "AWS access key"

        assert len(config.packages) == 2
        assert config.packages[0].name == "boto3"
        assert config.packages[0].ecosystem == "python"
        assert config.packages[1].ecosystem == "node"

        assert len(config.notes) == 2
        assert "terraform init" in config.notes[1]

    def test_shorthand_string_entries(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text(
            "dependencies:\n"
            "  cli_tools:\n"
            "    - jq\n"
            "    - rg\n"
            "  env_vars:\n"
            "    - MY_VAR\n"
            "  packages:\n"
            "    - requests\n"
        )
        config = read_preflight_yml(yml)
        assert config.cli_tools[0].name == "jq"
        assert config.cli_tools[1].name == "rg"
        assert config.env_vars[0].name == "MY_VAR"
        assert config.packages[0].name == "requests"

    def test_missing_file_returns_empty(self, tmp_path):
        missing = tmp_path / ".preflight.yml"
        config = read_preflight_yml(missing)
        assert isinstance(config, PreflightConfig)
        assert config.cli_tools == []
        assert config.env_vars == []
        assert config.packages == []
        assert config.notes == []

    def test_malformed_yaml_returns_empty(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text("{{invalid yaml: [[[")
        config = read_preflight_yml(yml)
        assert config.cli_tools == []
        assert config.env_vars == []

    def test_non_dict_top_level_returns_empty(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text("- just\n- a\n- list\n")
        config = read_preflight_yml(yml)
        assert config.cli_tools == []

    def test_empty_file_returns_empty(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text("")
        config = read_preflight_yml(yml)
        assert config.cli_tools == []

    def test_dependencies_not_a_dict(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text("dependencies: not_a_dict\n")
        config = read_preflight_yml(yml)
        assert config.cli_tools == []

    def test_cli_tools_not_a_list(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text(
            "dependencies:\n"
            "  cli_tools: not_a_list\n"
        )
        config = read_preflight_yml(yml)
        assert config.cli_tools == []

    def test_cli_tool_entry_missing_name(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text(
            "dependencies:\n"
            "  cli_tools:\n"
            "    - install_hint: brew install something\n"
        )
        config = read_preflight_yml(yml)
        assert config.cli_tools == []

    def test_unknown_ecosystem_defaults_to_python(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text(
            "dependencies:\n"
            "  packages:\n"
            "    - name: something\n"
            "      ecosystem: ruby\n"
        )
        config = read_preflight_yml(yml)
        assert config.packages[0].ecosystem == "python"

    def test_notes_with_non_string_scalars(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text(
            "notes:\n"
            "  - A string note\n"
            "  - 42\n"
            "  - true\n"
        )
        config = read_preflight_yml(yml)
        assert len(config.notes) == 3
        assert config.notes[0] == "A string note"
        assert config.notes[1] == "42"
        assert config.notes[2] == "True"

    def test_notes_not_a_list(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text("notes: just a string\n")
        config = read_preflight_yml(yml)
        assert config.notes == []

    def test_required_by_not_propagated_when_empty(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text(
            "dependencies:\n"
            "  cli_tools:\n"
            "    - name: git\n"
        )
        config = read_preflight_yml(yml)
        assert config.cli_tools[0].required_by == []

    def test_env_var_with_description(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text(
            "dependencies:\n"
            "  env_vars:\n"
            "    - name: DATABASE_URL\n"
            "      description: PostgreSQL connection string\n"
        )
        config = read_preflight_yml(yml, required_by="app")
        assert config.env_vars[0].name == "DATABASE_URL"
        assert config.env_vars[0].description == "PostgreSQL connection string"
        assert config.env_vars[0].required_by == ["app"]

    def test_no_dependencies_section(self, tmp_path):
        yml = tmp_path / ".preflight.yml"
        yml.write_text(
            "notes:\n"
            "  - Just notes, no deps\n"
        )
        config = read_preflight_yml(yml)
        assert config.cli_tools == []
        assert config.notes == ["Just notes, no deps"]

    def test_unexpected_entry_types_skipped(self, tmp_path):
        """Non-string, non-dict entries in cli_tools/env_vars/packages are skipped."""
        yml = tmp_path / ".preflight.yml"
        yml.write_text(
            "dependencies:\n"
            "  cli_tools:\n"
            "    - name: valid\n"
            "    - 42\n"
            "  env_vars:\n"
            "    - name: VALID_VAR\n"
            "    - [nested, list]\n"
            "  packages:\n"
            "    - name: valid-pkg\n"
            "    - 3.14\n"
        )
        config = read_preflight_yml(yml)
        assert len(config.cli_tools) == 1
        assert config.cli_tools[0].name == "valid"
        assert len(config.env_vars) == 1
        assert config.env_vars[0].name == "VALID_VAR"
        assert len(config.packages) == 1
        assert config.packages[0].name == "valid-pkg"
