"""Docker dependency scanner.

Detects Docker-related dependencies from Dockerfiles, compose files,
and docker run commands embedded in shell scripts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from agent_transfer.utils.preflight.manifest import DockerDep

try:
    import yaml

    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_DOCKERFILE_NAMES = {"Dockerfile"}
_DOCKERFILE_PREFIX = "Dockerfile."
_DOCKERFILE_SUFFIX = ".dockerfile"

_COMPOSE_NAMES = frozenset(
    {
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    }
)

# Matches "FROM image:tag" or "FROM image:tag AS alias", ignoring comments.
_FROM_RE = re.compile(
    r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", re.IGNORECASE | re.MULTILINE
)

# Matches "docker run" to detect presence.
_DOCKER_RUN_RE = re.compile(r"docker\s+run\s+")

# Short flags that take a separate value argument (e.g. -p 8080:80, -e FOO=bar).
_SHORT_FLAGS_WITH_VALUE = frozenset("e h l m p u v w".split())
# Long flags that take a separate value argument.
_LONG_FLAGS_WITH_VALUE = frozenset(
    [
        "--name",
        "--env",
        "--volume",
        "--publish",
        "--user",
        "--workdir",
        "--label",
        "--network",
        "--mount",
        "--cpus",
        "--memory",
        "--entrypoint",
        "--hostname",
        "--restart",
        "--pid",
        "--log-driver",
        "--log-opt",
    ]
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_image_from_docker_run(args_str: str) -> Optional[str]:
    """Parse tokens after ``docker run`` to find the image name.

    Skips flags (short and long) and their value arguments.
    The first non-flag token is the image name.
    """
    tokens = args_str.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--"):
            # Long flag: --name=value or --name value
            if "=" in tok:
                i += 1
                continue
            if tok in _LONG_FLAGS_WITH_VALUE and i + 1 < len(tokens):
                i += 2  # skip flag + value
                continue
            i += 1  # boolean long flag
            continue
        if tok.startswith("-") and not tok[1:].isdigit():
            # Short flag(s): -d, -it, -p 8080:80
            # Check if last char is a flag that takes a value
            flag_chars = tok[1:]
            if flag_chars and flag_chars[-1] in _SHORT_FLAGS_WITH_VALUE:
                i += 2  # skip flag + value
                continue
            i += 1  # boolean short flag(s)
            continue
        # First non-flag token = image name
        if tok.startswith("$"):
            return None  # variable reference, can't resolve
        return tok
    return None


def _is_dockerfile(path: Path) -> bool:
    """Return True if *path* looks like a Dockerfile."""
    name = path.name
    if name in _DOCKERFILE_NAMES:
        return True
    if name.startswith(_DOCKERFILE_PREFIX):
        return True
    if name.lower().endswith(_DOCKERFILE_SUFFIX):
        return True
    return False


def _extract_from_images(text: str) -> List[str]:
    """Extract image names from FROM directives in Dockerfile content."""
    images: List[str] = []
    for match in _FROM_RE.finditer(text):
        image = match.group(1)
        # Skip ARG-based variable references like $BASE_IMAGE
        if image.startswith("$"):
            continue
        images.append(image)
    return images


def _make_required_by(required_by: str) -> List[str]:
    return [required_by] if required_by else []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_for_dockerfiles(directory: Path, required_by: str = "") -> List[DockerDep]:
    """Find Dockerfiles in *directory* and return a list of :class:`DockerDep`.

    Each Dockerfile produces one ``DockerDep`` per FROM image found.  If the
    file cannot be read, it is silently skipped.
    """
    deps: List[DockerDep] = []
    req = _make_required_by(required_by)

    if not directory.is_dir():
        return deps

    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        if not _is_dockerfile(path):
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        images = _extract_from_images(text)
        if images:
            for image in images:
                deps.append(
                    DockerDep(
                        type="image",
                        file=str(path),
                        image=image,
                        required_by=list(req),
                    )
                )
        else:
            # Dockerfile exists but no parseable FROM -- still record it.
            deps.append(
                DockerDep(
                    type="image",
                    file=str(path),
                    required_by=list(req),
                )
            )

    return deps


def scan_for_compose(directory: Path, required_by: str = "") -> List[DockerDep]:
    """Find docker-compose files in *directory* and return :class:`DockerDep` items.

    When PyYAML is available the ``services`` key is parsed to extract
    service names.  If YAML parsing fails (or PyYAML is absent), the file
    is still recorded with an empty service list.
    """
    deps: List[DockerDep] = []
    req = _make_required_by(required_by)

    if not directory.is_dir():
        return deps

    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        if path.name not in _COMPOSE_NAMES:
            continue

        services: List[str] = []

        if _HAS_YAML:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                data = yaml.safe_load(text)
                if isinstance(data, dict) and "services" in data:
                    svc = data["services"]
                    if isinstance(svc, dict):
                        services = sorted(svc.keys())
            except Exception:  # noqa: BLE001
                # Malformed YAML -- record the file but skip parsing.
                pass

        deps.append(
            DockerDep(
                type="compose",
                file=str(path),
                services=services,
                required_by=list(req),
            )
        )

    return deps


def scan_docker_in_scripts(
    script_content: str, required_by: str = ""
) -> List[DockerDep]:
    """Extract ``docker run`` commands from *script_content*.

    Returns one :class:`DockerDep` per ``docker run`` invocation with the
    image name extracted when possible.
    """
    deps: List[DockerDep] = []
    req = _make_required_by(required_by)

    for match in _DOCKER_RUN_RE.finditer(script_content):
        # Get everything after "docker run " on the same line.
        rest = script_content[match.end() :].split("\n", 1)[0]
        image = _extract_image_from_docker_run(rest)

        deps.append(
            DockerDep(
                type="image",
                image=image,
                required_by=list(req),
            )
        )

    return deps


def scan_docker(
    directory: Path,
    script_files: Optional[List[Path]] = None,
    required_by: str = "",
) -> List[DockerDep]:
    """Unified Docker scanning entry point.

    Combines results from :func:`scan_for_dockerfiles`,
    :func:`scan_for_compose`, and :func:`scan_docker_in_scripts` (for each
    file in *script_files*).

    Parameters
    ----------
    directory:
        Root directory to scan for Dockerfiles and compose files.
    script_files:
        Optional list of script file paths whose content will be scanned
        for ``docker run`` commands.
    required_by:
        Label indicating what depends on these Docker artefacts.

    Returns
    -------
    list[DockerDep]
        Combined list of all detected Docker dependencies.
    """
    deps: List[DockerDep] = []

    deps.extend(scan_for_dockerfiles(directory, required_by=required_by))
    deps.extend(scan_for_compose(directory, required_by=required_by))

    if script_files:
        for script_path in script_files:
            try:
                content = script_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            deps.extend(scan_docker_in_scripts(content, required_by=required_by))

    return deps
