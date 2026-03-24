"""Preflight dependency scanners.

Each scanner is an independent module that detects a specific category
of dependencies from agent/skill/hook/config files.

Scanners:
    mcp_scanner — MCP server detection and provenance
    script_scanner — CLI tools and env vars from scripts
    binary_scanner — ELF compiled binary detection
    git_scanner — Git remote URL extraction
    docker_scanner — Dockerfile/compose detection
    preflight_yml — .preflight.yml author declarations
"""
