"""Remediation hint database.

Maps dependency names to actionable installation commands and guidance.
Used by the checker to provide helpful remediation suggestions in reports.
"""

from typing import Dict, Optional


# CLI tool install hints keyed by tool name
CLI_TOOL_HINTS: Dict[str, str] = {
    "node": "Install via: curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt-get install -y nodejs",
    "npm": "Installed with Node.js. See: https://nodejs.org/",
    "npx": "Installed with Node.js (npm >= 5.2). See: https://nodejs.org/",
    "bun": "Install via: curl -fsSL https://bun.sh/install | bash",
    "uv": "Install via: curl -LsSf https://astral.sh/uv/install.sh | sh",
    "pip": "Usually bundled with Python. Try: python3 -m ensurepip --upgrade",
    "python3": "Install via: sudo apt-get install python3",
    "git": "Install via: sudo apt-get install git",
    "docker": "Install via: https://docs.docker.com/engine/install/",
    "docker-compose": "Install via: sudo apt-get install docker-compose-plugin",
    "cargo": "Install via: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
    "rustc": "Install via: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
    "jq": "Install via: sudo apt-get install jq",
    "curl": "Install via: sudo apt-get install curl",
    "wget": "Install via: sudo apt-get install wget",
    "rg": "Install via: sudo apt-get install ripgrep",
    "fd": "Install via: sudo apt-get install fd-find",
    "fzf": "Install via: sudo apt-get install fzf",
    "tree": "Install via: sudo apt-get install tree",
    "make": "Install via: sudo apt-get install build-essential",
    "gcc": "Install via: sudo apt-get install build-essential",
    "g++": "Install via: sudo apt-get install build-essential",
}

# Runtime install hints for MCP server dependencies
RUNTIME_HINTS: Dict[str, str] = {
    "node": "Install Node.js LTS: https://nodejs.org/",
    "python": "Install Python 3.8+: sudo apt-get install python3",
    "uv": "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh",
    "bun": "Install Bun: curl -fsSL https://bun.sh/install | bash",
    "docker": "Install Docker: https://docs.docker.com/engine/install/",
}

# Setup method hints for git repo dependencies
SETUP_METHOD_HINTS: Dict[str, str] = {
    "python-venv": "python3 -m venv .venv && source .venv/bin/activate && pip install -e .",
    "uv": "uv sync",
    "npm": "npm install",
    "cargo": "cargo build --release",
    "docker": "docker build -t <name> .",
    "pip": "pip install -e .",
}

# Package ecosystem hints
PACKAGE_ECOSYSTEM_HINTS: Dict[str, str] = {
    "python": "pip install {name}",
    "node": "npm install {name}",
}


def get_cli_hint(tool_name: str) -> Optional[str]:
    """Get installation hint for a CLI tool."""
    return CLI_TOOL_HINTS.get(tool_name)


def get_runtime_hint(runtime: str) -> Optional[str]:
    """Get installation hint for a runtime."""
    return RUNTIME_HINTS.get(runtime)


def get_setup_hint(setup_method: str) -> Optional[str]:
    """Get setup hint for a git repo setup method."""
    return SETUP_METHOD_HINTS.get(setup_method)


def get_package_hint(ecosystem: str, name: str) -> Optional[str]:
    """Get installation hint for a package."""
    template = PACKAGE_ECOSYSTEM_HINTS.get(ecosystem)
    if template:
        return template.format(name=name)
    return None
