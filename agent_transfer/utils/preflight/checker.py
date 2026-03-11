"""Preflight checker data models and validation logic.

CheckResult and ReadinessReport dataclasses for representing
the outcome of dependency checks against the local environment.
"""

import importlib
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_transfer.utils.preflight.manifest import (
    BinaryDep,
    CliToolDep,
    DockerDep,
    EnvVarDep,
    GitRepoDep,
    McpServerDep,
    PackageDep,
    SkillTreeDep,
    SourcedFileDep,
)
from agent_transfer.utils.preflight.remediation import (
    get_cli_hint,
    get_package_hint,
    get_runtime_hint,
    get_setup_hint,
)


@dataclass
class CheckResult:
    """Result of checking a single dependency."""

    dependency: Any  # One of the *Dep dataclasses from manifest.py
    status: str = "RED"  # "GREEN", "YELLOW", "RED"
    message: str = ""
    remediation: Optional[str] = None


@dataclass
class ReadinessReport:
    """Aggregated results of all preflight checks."""

    manifest: Any = None  # TransferManifest
    target_os: str = ""
    target_arch: str = ""
    results: Dict[str, List[CheckResult]] = field(default_factory=dict)
    overall_status: str = "PASS"  # "PASS", "WARN", "FAIL"
    green_count: int = 0
    yellow_count: int = 0
    red_count: int = 0
    manual_checklist: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Individual dependency checkers
# ---------------------------------------------------------------------------


def check_mcp(dep: McpServerDep) -> CheckResult:
    """Check MCP server readiness.

    GREEN if runtime found + local_path exists.
    YELLOW if runtime found but no local_path.
    RED if runtime missing.
    """
    runtime_found = shutil.which(dep.runtime) is not None

    if not runtime_found:
        return CheckResult(
            dependency=dep,
            status="RED",
            message=f"MCP server '{dep.id}': runtime '{dep.runtime}' not found on PATH",
            remediation=get_runtime_hint(dep.runtime),
        )

    if dep.local_path:
        local = Path(dep.local_path).expanduser()
        if local.exists():
            return CheckResult(
                dependency=dep,
                status="GREEN",
                message=f"MCP server '{dep.id}': runtime '{dep.runtime}' found, local path exists",
            )
        else:
            return CheckResult(
                dependency=dep,
                status="YELLOW",
                message=f"MCP server '{dep.id}': runtime '{dep.runtime}' found, but local_path '{dep.local_path}' missing",
                remediation=f"Clone or install MCP server to {dep.local_path}",
            )

    return CheckResult(
        dependency=dep,
        status="YELLOW",
        message=f"MCP server '{dep.id}': runtime '{dep.runtime}' found, no local_path specified",
    )


def check_cli(dep: CliToolDep) -> CheckResult:
    """Check CLI tool availability via shutil.which().

    GREEN if found. YELLOW if optional and missing. RED if required and missing.
    """
    if shutil.which(dep.name) is not None:
        return CheckResult(
            dependency=dep,
            status="GREEN",
            message=f"CLI tool '{dep.name}' found on PATH",
        )

    hint = dep.install_hint or get_cli_hint(dep.name)
    if dep.optional:
        return CheckResult(
            dependency=dep,
            status="YELLOW",
            message=f"Optional CLI tool '{dep.name}' not found on PATH",
            remediation=hint,
        )

    return CheckResult(
        dependency=dep,
        status="RED",
        message=f"Required CLI tool '{dep.name}' not found on PATH",
        remediation=hint,
    )


def check_env(dep: EnvVarDep) -> CheckResult:
    """Check env var presence via os.environ.

    GREEN if set. YELLOW if not critical and missing. RED if critical and missing.
    NEVER logs the value (R8 compliance).
    """
    is_set = os.environ.get(dep.name) is not None

    if is_set:
        return CheckResult(
            dependency=dep,
            status="GREEN",
            message=f"Environment variable '{dep.name}' is set",
        )

    if dep.critical:
        return CheckResult(
            dependency=dep,
            status="RED",
            message=f"Critical environment variable '{dep.name}' is NOT set",
            remediation=f"export {dep.name}=<value>",
        )

    return CheckResult(
        dependency=dep,
        status="YELLOW",
        message=f"Environment variable '{dep.name}' is not set (non-critical)",
        remediation=f"export {dep.name}=<value>",
    )


def check_git_repos(dep: GitRepoDep) -> CheckResult:
    """Check if expected git repo path exists.

    GREEN if dir exists with .git. YELLOW if dir exists without .git.
    RED if directory missing.
    """
    repo_path = Path(dep.local_path).expanduser()

    if not repo_path.is_dir():
        hint = get_setup_hint(dep.setup_method)
        clone_msg = f"git clone {dep.repo_url} {dep.local_path}" if dep.repo_url else None
        remediation = clone_msg or hint
        return CheckResult(
            dependency=dep,
            status="RED",
            message=f"Git repo '{dep.name}': directory '{dep.local_path}' does not exist",
            remediation=remediation,
        )

    git_dir = repo_path / ".git"
    if git_dir.exists():
        return CheckResult(
            dependency=dep,
            status="GREEN",
            message=f"Git repo '{dep.name}': directory exists with .git",
        )

    return CheckResult(
        dependency=dep,
        status="YELLOW",
        message=f"Git repo '{dep.name}': directory exists but no .git found",
        remediation=f"Directory '{dep.local_path}' exists but is not a git repository. "
        f"Try: cd {dep.local_path} && git init",
    )


def check_binaries(dep: BinaryDep) -> CheckResult:
    """Check binary existence and architecture.

    GREEN if exists + arch matches current platform.
    YELLOW if exists + arch mismatch.
    RED if binary missing.
    """
    binary_path = Path(dep.path).expanduser()

    if not binary_path.exists():
        which_result = shutil.which(dep.name)
        if which_result is None:
            remediation = None
            if dep.build_command:
                remediation = f"Build from source: {dep.build_command}"
            elif dep.source_repo:
                remediation = f"Clone and build: {dep.source_repo}"
            return CheckResult(
                dependency=dep,
                status="RED",
                message=f"Binary '{dep.name}' not found at '{dep.path}' or on PATH",
                remediation=remediation,
            )
        # Found on PATH even though dep.path doesn't exist
        binary_path = Path(which_result)

    # Binary exists; check architecture if specified
    if dep.arch:
        current_arch = platform.machine()
        if dep.arch.lower() != current_arch.lower():
            return CheckResult(
                dependency=dep,
                status="YELLOW",
                message=f"Binary '{dep.name}' exists but arch mismatch: "
                f"binary='{dep.arch}', system='{current_arch}'",
                remediation=f"Rebuild for {current_arch}" + (
                    f": {dep.build_command}" if dep.build_command else ""
                ),
            )

    return CheckResult(
        dependency=dep,
        status="GREEN",
        message=f"Binary '{dep.name}' found and architecture is compatible",
    )


def check_skill_trees(dep: SkillTreeDep) -> CheckResult:
    """Check skill tree installation.

    GREEN if install_path exists.
    YELLOW if exists but missing system_deps.
    RED if install_path missing.
    """
    install_path = Path(dep.install_path).expanduser()

    if not install_path.is_dir():
        remediation = None
        if dep.install_script:
            remediation = f"Run install script: {dep.install_script}"
        return CheckResult(
            dependency=dep,
            status="RED",
            message=f"Skill tree '{dep.name}': install path '{dep.install_path}' not found",
            remediation=remediation,
        )

    # Check system_deps are available
    missing_deps = []
    for sys_dep in dep.system_deps:
        if shutil.which(sys_dep) is None:
            missing_deps.append(sys_dep)

    if missing_deps:
        return CheckResult(
            dependency=dep,
            status="YELLOW",
            message=f"Skill tree '{dep.name}': installed, but missing system deps: "
            f"{', '.join(missing_deps)}",
            remediation=f"Install missing dependencies: {', '.join(missing_deps)}",
        )

    return CheckResult(
        dependency=dep,
        status="GREEN",
        message=f"Skill tree '{dep.name}' found at '{dep.install_path}'",
    )


def check_docker(dep: DockerDep) -> CheckResult:
    """Check Docker availability.

    GREEN if docker is on PATH. YELLOW if docker exists but compose file missing.
    RED if docker not found.
    """
    if shutil.which("docker") is None:
        return CheckResult(
            dependency=dep,
            status="RED",
            message="Docker not found on PATH",
            remediation=get_cli_hint("docker"),
        )

    # If a compose file is referenced, check it exists
    if dep.file:
        compose_path = Path(dep.file).expanduser()
        if not compose_path.exists():
            return CheckResult(
                dependency=dep,
                status="YELLOW",
                message=f"Docker found, but compose file '{dep.file}' is missing",
                remediation=f"Create or restore compose file at {dep.file}",
            )

    return CheckResult(
        dependency=dep,
        status="GREEN",
        message="Docker is available" + (
            f" and compose file '{dep.file}' exists" if dep.file else ""
        ),
    )


def check_packages(dep: PackageDep) -> CheckResult:
    """Check package availability.

    For python: uses importlib. For node: uses npm list.
    GREEN if found. YELLOW if optional-style miss. RED if missing.
    """
    if dep.ecosystem == "python":
        # Normalize package name for import (e.g. my-package -> my_package)
        import_name = dep.name.replace("-", "_")
        try:
            importlib.import_module(import_name)
            return CheckResult(
                dependency=dep,
                status="GREEN",
                message=f"Python package '{dep.name}' is importable",
            )
        except ImportError:
            return CheckResult(
                dependency=dep,
                status="RED",
                message=f"Python package '{dep.name}' not found",
                remediation=get_package_hint("python", dep.name),
            )

    elif dep.ecosystem == "node":
        if shutil.which("npm") is None:
            return CheckResult(
                dependency=dep,
                status="RED",
                message=f"Node package '{dep.name}' check failed: npm not on PATH",
                remediation=get_cli_hint("npm"),
            )
        try:
            result = subprocess.run(
                ["npm", "list", dep.name, "--depth=0"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and dep.name in result.stdout:
                return CheckResult(
                    dependency=dep,
                    status="GREEN",
                    message=f"Node package '{dep.name}' is installed",
                )
            else:
                return CheckResult(
                    dependency=dep,
                    status="RED",
                    message=f"Node package '{dep.name}' not found via npm list",
                    remediation=get_package_hint("node", dep.name),
                )
        except (subprocess.TimeoutExpired, OSError):
            return CheckResult(
                dependency=dep,
                status="YELLOW",
                message=f"Node package '{dep.name}': npm list timed out or failed",
                remediation=get_package_hint("node", dep.name),
            )

    # Unknown ecosystem
    return CheckResult(
        dependency=dep,
        status="YELLOW",
        message=f"Package '{dep.name}': unknown ecosystem '{dep.ecosystem}', cannot verify",
    )


def check_sourced_files(dep: SourcedFileDep) -> CheckResult:
    """Check if sourced file exists.

    GREEN if exists. RED if missing.
    """
    file_path = Path(dep.path).expanduser()

    if file_path.exists():
        return CheckResult(
            dependency=dep,
            status="GREEN",
            message=f"Sourced file '{dep.path}' exists",
        )

    return CheckResult(
        dependency=dep,
        status="RED",
        message=f"Sourced file '{dep.path}' not found",
        remediation=f"Restore or recreate the file at {dep.path}",
    )
