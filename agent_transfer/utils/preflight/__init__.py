"""Preflight transfer readiness validation.

Public API:
    collect_inventory() — Scan agents/skills/hooks/configs and build dependency manifest
    run_preflight_checks() — Validate target environment against manifest
    write_manifest() / read_manifest() / read_manifest_from_archive() — Manifest I/O
    display_preflight_report() / report_to_json() — Report output
"""

from agent_transfer.utils.preflight.manifest import (
    TransferManifest,
    read_manifest,
    read_manifest_from_archive,
    write_manifest,
)
from agent_transfer.utils.preflight.collector import collect_inventory
from agent_transfer.utils.preflight.checker import (
    CheckResult,
    ReadinessReport,
    check_mcp,
    check_cli,
    check_env,
    check_git_repos,
    check_binaries,
    check_skill_trees,
    check_docker,
    check_packages,
    check_sourced_files,
)

import platform as _platform_mod


def run_preflight_checks(manifest: TransferManifest) -> ReadinessReport:
    """Run all dependency checks against the local environment.

    Checks (in order):
    1. MCP server configuration
    2. CLI tool availability (PATH lookup)
    3. Environment variable presence (NEVER values)
    4. Git repo directory existence
    5. Compiled binary existence + architecture match
    6. Skill tree existence + system deps
    7. Docker availability
    8. Python/Node package availability
    9. Sourced file existence
    """
    results = {}  # type: dict
    deps = manifest.dependencies

    # Category → (checker_func, dep_list)
    checks = [
        ("mcp_servers", check_mcp, deps.mcp_servers),
        ("cli_tools", check_cli, deps.cli_tools),
        ("env_vars", check_env, deps.env_vars),
        ("git_repos", check_git_repos, deps.git_repos),
        ("compiled_binaries", check_binaries, deps.compiled_binaries),
        ("skill_trees", check_skill_trees, deps.skill_trees),
        ("docker", check_docker, deps.docker),
        ("packages", check_packages, deps.python_packages),
        ("sourced_files", check_sourced_files, deps.sourced_files),
    ]

    green = 0
    yellow = 0
    red = 0

    for category, checker, dep_list in checks:
        category_results = []
        for dep in dep_list:
            result = checker(dep)
            category_results.append(result)
            if result.status == "GREEN":
                green += 1
            elif result.status == "YELLOW":
                yellow += 1
            else:
                red += 1
        if category_results:
            results[category] = category_results

    # Determine overall status
    if red > 0:
        overall = "FAIL"
    elif yellow > 0:
        overall = "WARN"
    else:
        overall = "PASS"

    return ReadinessReport(
        manifest=manifest,
        target_os=_platform_mod.system().lower(),
        target_arch=_platform_mod.machine(),
        results=results,
        overall_status=overall,
        green_count=green,
        yellow_count=yellow,
        red_count=red,
    )


__all__ = [
    "collect_inventory",
    "run_preflight_checks",
    "write_manifest",
    "read_manifest",
    "read_manifest_from_archive",
    "TransferManifest",
    "CheckResult",
    "ReadinessReport",
]
