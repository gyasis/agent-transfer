"""Script scanner -- extracts CLI tool refs and env var refs from scripts.

Scans .sh, .py, and .js files for:
- CLI tool invocations (direct calls, ``which``, ``command -v``, subshells)
- Environment variable references (shell ``$VAR`` / ``${VAR}``, Python
  ``os.environ`` / ``os.getenv``, Node ``process.env``)
- Source/import statements (``source``, ``. file``, ``from X import``,
  ``require("X")``)

**R8 compliance**: only env-var *names* are captured, never values.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set

from agent_transfer.utils.preflight.manifest import (
    CliToolDep,
    EnvVarDep,
    PackageDep,
    SourcedFileDep,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KNOWN_CLI_TOOLS: Set[str] = {
    "git", "docker", "node", "npm", "npx", "bun", "bunx",
    "uv", "pip", "python3", "cargo", "rustc", "make", "gcc",
    "jq", "curl", "wget", "rg", "fd", "fzf",
}

_SUPPORTED_EXTENSIONS: Set[str] = {".sh", ".py", ".js"}

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# CLI tool usage --------------------------------------------------------

# Line starts with a known tool name (possibly after whitespace).
# Captures the tool name in group 1.
_RE_LINE_START_TOOL = re.compile(
    r"^\s*(" + "|".join(re.escape(t) for t in sorted(KNOWN_CLI_TOOLS)) + r")\b",
    re.MULTILINE,
)

# ``which <tool>`` or ``command -v <tool>``
_RE_WHICH = re.compile(
    r"\bwhich\s+(\S+)",
)
_RE_COMMAND_V = re.compile(
    r"\bcommand\s+-v\s+(\S+)",
)

# Backtick / $() subshell invocations containing a known tool.
_RE_SUBSHELL = re.compile(
    r"(?:`|\$\()\s*(" + "|".join(re.escape(t) for t in sorted(KNOWN_CLI_TOOLS)) + r")\b",
)

# Pipe targets: ``| tool``
_RE_PIPE_TOOL = re.compile(
    r"\|\s*(" + "|".join(re.escape(t) for t in sorted(KNOWN_CLI_TOOLS)) + r")\b",
)

# Environment variables -------------------------------------------------

# Shell-style: $VAR or ${VAR}  (must start with a letter or underscore)
_RE_ENV_SHELL = re.compile(
    r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?",
)

# Python os.environ["VAR"] / os.environ['VAR'] / os.environ.get("VAR")
_RE_ENV_PYTHON_BRACKET = re.compile(
    r"""os\.environ\[['"]([A-Za-z_][A-Za-z0-9_]*)['"]\]""",
)
_RE_ENV_PYTHON_GET = re.compile(
    r"""os\.environ\.get\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]""",
)

# Python os.getenv("VAR")
_RE_ENV_PYTHON_GETENV = re.compile(
    r"""os\.getenv\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]""",
)

# Node process.env.VAR
_RE_ENV_NODE = re.compile(
    r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)",
)

# Source / import -------------------------------------------------------

# Shell: ``source file`` or ``. file`` (dot-space)
_RE_SOURCE_SH = re.compile(
    r"^\s*(?:source|\.)\s+[\"']?([^\s\"'#]+)[\"']?",
    re.MULTILINE,
)

# Python: ``from X import ...`` or ``import X``
_RE_IMPORT_PYTHON_FROM = re.compile(
    r"^\s*from\s+([\w.]+)\s+import\b",
    re.MULTILINE,
)
_RE_IMPORT_PYTHON = re.compile(
    r"^\s*import\s+([\w.]+)",
    re.MULTILINE,
)

# Node: ``require("X")`` or ``require('X')``
_RE_REQUIRE_NODE = re.compile(
    r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)""",
)

# ---------------------------------------------------------------------------
# Shell built-ins and positional vars to ignore
# ---------------------------------------------------------------------------

_SHELL_INTERNALS: Set[str] = {
    # Positional / special parameters
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "#", "?", "@", "*", "!", "-", "$",
    # Common shell-set variables (not real env dependencies)
    "BASH", "BASH_SOURCE", "BASHPID", "BASH_VERSINFO",
    "BASH_VERSION", "LINENO", "FUNCNAME", "PIPESTATUS",
    "RANDOM", "SECONDS", "SHLVL", "PPID", "UID", "EUID",
    "IFS", "PWD", "OLDPWD", "OPTARG", "OPTIND", "REPLY",
    "_",
}

# Python standard-library top-level modules we never report as packages.
_PYTHON_STDLIB: Set[str] = {
    "abc", "argparse", "ast", "asyncio", "atexit", "base64",
    "binascii", "builtins", "calendar", "cgi", "cmd", "codecs",
    "collections", "colorsys", "compileall", "concurrent",
    "configparser", "contextlib", "contextvars", "copy", "csv",
    "ctypes", "dataclasses", "datetime", "decimal", "difflib",
    "dis", "email", "enum", "errno", "fcntl", "filecmp",
    "fileinput", "fnmatch", "fractions", "ftplib", "functools",
    "gc", "getopt", "getpass", "gettext", "glob", "grp", "gzip",
    "hashlib", "heapq", "hmac", "html", "http", "imaplib",
    "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "linecache", "locale", "logging",
    "lzma", "mailbox", "math", "mimetypes", "mmap", "multiprocessing",
    "netrc", "numbers", "operator", "os", "pathlib", "pdb",
    "pickle", "pickletools", "pipes", "pkgutil", "platform",
    "plistlib", "poplib", "posix", "posixpath", "pprint",
    "profile", "pstats", "pty", "pwd", "py_compile",
    "pydoc", "queue", "quopri", "random", "re", "readline",
    "reprlib", "resource", "rlcompleter", "runpy", "sched",
    "secrets", "select", "selectors", "shelve", "shlex", "shutil",
    "signal", "site", "smtpd", "smtplib", "sndhdr", "socket",
    "socketserver", "sqlite3", "ssl", "stat", "statistics",
    "string", "stringprep", "struct", "subprocess", "sunau",
    "symtable", "sys", "sysconfig", "syslog", "tabnanny",
    "tarfile", "tempfile", "termios", "test", "textwrap",
    "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "trace", "traceback", "tracemalloc", "tty",
    "turtle", "turtledemo", "types", "typing", "unicodedata",
    "unittest", "urllib", "uu", "uuid", "venv", "warnings",
    "wave", "weakref", "webbrowser", "winreg", "winsound",
    "wsgiref", "xdrlib", "xml", "xmlrpc", "zipapp",
    "zipfile", "zipimport", "zlib",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_real_env_var(name: str) -> bool:
    """Return True if *name* looks like a genuine env-var dependency."""
    if name in _SHELL_INTERNALS:
        return False
    # Single-char names that are shell specials
    if len(name) == 1 and not name.isalpha():
        return False
    return True


def _top_level_module(dotted: str) -> str:
    """Return the top-level package name from a dotted import path."""
    return dotted.split(".")[0]


def _classify_extension(path: Path) -> str:
    """Return 'sh', 'py', 'js', or '' for unsupported files."""
    suffix = path.suffix.lower()
    return {".sh": "sh", ".py": "py", ".js": "js"}.get(suffix, "")


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------


def scan_script_file(file_path: Path, required_by: str = "") -> Dict[str, list]:
    """Scan a single script file for dependencies.

    Parameters
    ----------
    file_path:
        Path to a ``.sh``, ``.py``, or ``.js`` file.
    required_by:
        Optional label indicating what component needs this file
        (propagated into each dependency's ``required_by`` list).

    Returns
    -------
    dict
        Keys: ``cli_tools``, ``env_vars``, ``sourced_files``, ``packages``.
        Values are lists of the corresponding manifest dataclasses.
    """
    result: Dict[str, list] = {
        "cli_tools": [],
        "env_vars": [],
        "sourced_files": [],
        "packages": [],
    }

    file_path = Path(file_path)
    lang = _classify_extension(file_path)
    if not lang:
        return result

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result

    req_list = [required_by] if required_by else []

    # --- CLI tools ---
    cli_names: Set[str] = set()

    for m in _RE_LINE_START_TOOL.finditer(text):
        cli_names.add(m.group(1))

    for m in _RE_WHICH.finditer(text):
        candidate = m.group(1)
        if candidate in KNOWN_CLI_TOOLS:
            cli_names.add(candidate)

    for m in _RE_COMMAND_V.finditer(text):
        candidate = m.group(1)
        if candidate in KNOWN_CLI_TOOLS:
            cli_names.add(candidate)

    for m in _RE_SUBSHELL.finditer(text):
        cli_names.add(m.group(1))

    for m in _RE_PIPE_TOOL.finditer(text):
        cli_names.add(m.group(1))

    result["cli_tools"] = [
        CliToolDep(name=n, required_by=list(req_list))
        for n in sorted(cli_names)
    ]

    # --- Env vars (names only -- R8 compliance) ---
    env_names: Set[str] = set()

    if lang == "sh":
        for m in _RE_ENV_SHELL.finditer(text):
            name = m.group(1)
            if _is_real_env_var(name):
                env_names.add(name)

    if lang == "py":
        for pat in (_RE_ENV_PYTHON_BRACKET, _RE_ENV_PYTHON_GET, _RE_ENV_PYTHON_GETENV):
            for m in pat.finditer(text):
                env_names.add(m.group(1))
        # Also pick up shell-style expansion in Python f-strings / subprocess
        for m in _RE_ENV_SHELL.finditer(text):
            name = m.group(1)
            if _is_real_env_var(name):
                env_names.add(name)

    if lang == "js":
        for m in _RE_ENV_NODE.finditer(text):
            env_names.add(m.group(1))

    result["env_vars"] = [
        EnvVarDep(name=n, required_by=list(req_list))
        for n in sorted(env_names)
    ]

    # --- Source / import ---
    sourced_paths: Set[str] = set()
    package_names: Set[str] = set()

    if lang == "sh":
        for m in _RE_SOURCE_SH.finditer(text):
            sourced_paths.add(m.group(1))

    if lang == "py":
        for m in _RE_IMPORT_PYTHON_FROM.finditer(text):
            top = _top_level_module(m.group(1))
            if top not in _PYTHON_STDLIB:
                package_names.add(top)
        for m in _RE_IMPORT_PYTHON.finditer(text):
            top = _top_level_module(m.group(1))
            if top not in _PYTHON_STDLIB:
                package_names.add(top)

    if lang == "js":
        for m in _RE_REQUIRE_NODE.finditer(text):
            pkg = m.group(1)
            # Relative paths are sourced files, not packages
            if pkg.startswith(".") or pkg.startswith("/"):
                sourced_paths.add(pkg)
            else:
                # Scoped packages: @scope/pkg -> keep full name
                package_names.add(pkg)

    result["sourced_files"] = [
        SourcedFileDep(path=p, required_by=list(req_list))
        for p in sorted(sourced_paths)
    ]

    result["packages"] = [
        PackageDep(
            name=n,
            ecosystem="python" if lang == "py" else "node",
            required_by=list(req_list),
        )
        for n in sorted(package_names)
    ]

    return result


# ---------------------------------------------------------------------------
# Multi-file scanner with dedup/merge
# ---------------------------------------------------------------------------


def scan_scripts(
    file_paths: List[Path],
    required_by: str = "",
) -> Dict[str, list]:
    """Scan multiple script files and merge deduplicated results.

    Parameters
    ----------
    file_paths:
        Iterable of ``Path`` objects to scan.
    required_by:
        Optional label propagated to all discovered dependencies.

    Returns
    -------
    dict
        Merged dict with keys ``cli_tools``, ``env_vars``,
        ``sourced_files``, ``packages``.
    """
    # Accumulators keyed by the dependency's identity (name or path).
    cli_map: Dict[str, CliToolDep] = {}
    env_map: Dict[str, EnvVarDep] = {}
    src_map: Dict[str, SourcedFileDep] = {}
    pkg_map: Dict[str, PackageDep] = {}

    for fp in file_paths:
        single = scan_script_file(Path(fp), required_by=required_by)

        for dep in single["cli_tools"]:
            if dep.name in cli_map:
                _merge_required_by(cli_map[dep.name], dep)
            else:
                cli_map[dep.name] = dep

        for dep in single["env_vars"]:
            if dep.name in env_map:
                _merge_required_by(env_map[dep.name], dep)
            else:
                env_map[dep.name] = dep

        for dep in single["sourced_files"]:
            if dep.path in src_map:
                _merge_required_by(src_map[dep.path], dep)
            else:
                src_map[dep.path] = dep

        for dep in single["packages"]:
            if dep.name in pkg_map:
                _merge_required_by(pkg_map[dep.name], dep)
            else:
                pkg_map[dep.name] = dep

    return {
        "cli_tools": sorted(cli_map.values(), key=lambda d: d.name),
        "env_vars": sorted(env_map.values(), key=lambda d: d.name),
        "sourced_files": sorted(src_map.values(), key=lambda d: d.path),
        "packages": sorted(pkg_map.values(), key=lambda d: d.name),
    }


def _merge_required_by(existing: object, incoming: object) -> None:
    """Merge ``required_by`` lists in-place, avoiding duplicates."""
    for entry in incoming.required_by:  # type: ignore[attr-defined]
        if entry not in existing.required_by:  # type: ignore[attr-defined]
            existing.required_by.append(entry)  # type: ignore[attr-defined]
