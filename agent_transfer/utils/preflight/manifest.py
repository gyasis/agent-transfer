"""Transfer manifest data models and I/O.

Defines all dependency dataclasses and the TransferManifest root document
that gets bundled as manifest.json in export archives.
"""

import json
import tarfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# --- Dependency Types ---


@dataclass
class McpServerDep:
    """An MCP server dependency with installation provenance."""

    id: str
    install_type: str = "unknown"
    repo_url: Optional[str] = None
    local_path: Optional[str] = None
    package: Optional[str] = None
    endpoint: Optional[str] = None
    setup_commands: List[str] = field(default_factory=list)
    runtime: str = "node"
    auth_required: bool = False
    env_vars: List[str] = field(default_factory=list)
    required_by: List[str] = field(default_factory=list)


@dataclass
class GitRepoDep:
    """A git repository that needs to be cloned on the target."""

    name: str
    repo_url: str = ""
    local_path: str = ""
    setup_method: str = "pip"
    setup_commands: List[str] = field(default_factory=list)
    required_by: List[str] = field(default_factory=list)


@dataclass
class BinaryDep:
    """A compiled binary with architecture metadata."""

    name: str
    path: str = ""
    arch: str = ""
    os: str = ""
    source_lang: Optional[str] = None
    build_command: Optional[str] = None
    source_repo: Optional[str] = None
    required_by: List[str] = field(default_factory=list)


@dataclass
class SkillTreeDep:
    """A self-contained skill installation tree."""

    name: str
    install_path: str = ""
    install_script: Optional[str] = None
    system_deps: List[str] = field(default_factory=list)
    optional_deps: List[str] = field(default_factory=list)
    compiled_binaries: List[str] = field(default_factory=list)
    env_vars_set: List[str] = field(default_factory=list)
    path_additions: List[str] = field(default_factory=list)
    required_by: List[str] = field(default_factory=list)


@dataclass
class CliToolDep:
    """A CLI tool expected on the system PATH."""

    name: str
    version_hint: Optional[str] = None
    install_hint: Optional[str] = None
    optional: bool = False
    required_by: List[str] = field(default_factory=list)


@dataclass
class EnvVarDep:
    """An environment variable dependency. NEVER stores the value."""

    name: str
    description: Optional[str] = None
    critical: bool = False
    required_by: List[str] = field(default_factory=list)


@dataclass
class DockerDep:
    """A Docker/container dependency."""

    type: str = "image"
    file: Optional[str] = None
    image: Optional[str] = None
    services: List[str] = field(default_factory=list)
    required_by: List[str] = field(default_factory=list)


@dataclass
class PackageDep:
    """A Python or Node package dependency."""

    name: str
    version_hint: Optional[str] = None
    ecosystem: str = "python"
    required_by: List[str] = field(default_factory=list)


@dataclass
class SourcedFileDep:
    """A file sourced/imported by a script."""

    path: str
    required_by: List[str] = field(default_factory=list)


# --- Composite Structures ---


@dataclass
class ContentsInventory:
    """Itemized list of what's physically in the archive."""

    agents: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    hooks: List[str] = field(default_factory=list)
    configs: List[str] = field(default_factory=list)


@dataclass
class DependencyGraph:
    """All external requirements organized by category."""

    mcp_servers: List[McpServerDep] = field(default_factory=list)
    git_repos: List[GitRepoDep] = field(default_factory=list)
    compiled_binaries: List[BinaryDep] = field(default_factory=list)
    skill_trees: List[SkillTreeDep] = field(default_factory=list)
    cli_tools: List[CliToolDep] = field(default_factory=list)
    env_vars: List[EnvVarDep] = field(default_factory=list)
    docker: List[DockerDep] = field(default_factory=list)
    packages: List[PackageDep] = field(default_factory=list)
    sourced_files: List[SourcedFileDep] = field(default_factory=list)


@dataclass
class TransferManifest:
    """Root document bundled in export archives as manifest.json."""

    manifest_version: str = "2.0"
    created_at: str = ""
    source_platform: str = "claude-code"
    source_os: str = ""
    source_arch: str = ""
    source_home: str = ""
    contents: ContentsInventory = field(default_factory=ContentsInventory)
    dependencies: DependencyGraph = field(default_factory=DependencyGraph)


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------

# Maps for deserializing dependency lists back into typed dataclasses.
_DEP_TYPE_MAP: Dict[str, type] = {
    "mcp_servers": McpServerDep,
    "git_repos": GitRepoDep,
    "compiled_binaries": BinaryDep,
    "skill_trees": SkillTreeDep,
    "cli_tools": CliToolDep,
    "env_vars": EnvVarDep,
    "docker": DockerDep,
    "packages": PackageDep,
    "sourced_files": SourcedFileDep,
}


def _manifest_to_dict(manifest: TransferManifest) -> Dict[str, Any]:
    """Convert manifest to a JSON-serializable dict."""
    return asdict(manifest)


def _filter_fields(cls: type, item: Dict[str, Any]) -> Dict[str, Any]:
    """Filter a dict to only include keys matching dataclass fields.

    Provides forward-compatibility: manifests from newer versions with
    extra fields won't crash older readers.
    """
    import dataclasses

    valid_keys = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in item.items() if k in valid_keys}


def _dict_to_manifest(data: Dict[str, Any]) -> TransferManifest:
    """Reconstruct a TransferManifest from a dict (parsed JSON)."""
    contents_data = data.get("contents", {})
    contents = ContentsInventory(
        agents=contents_data.get("agents", []),
        skills=contents_data.get("skills", []),
        hooks=contents_data.get("hooks", []),
        configs=contents_data.get("configs", []),
    )

    deps_data = data.get("dependencies", {})
    dep_kwargs = {}  # type: Dict[str, list]
    for key, cls in _DEP_TYPE_MAP.items():
        items = deps_data.get(key, [])
        dep_kwargs[key] = [
            cls(**_filter_fields(cls, item)) for item in items if isinstance(item, dict)
        ]

    dependencies = DependencyGraph(**dep_kwargs)

    return TransferManifest(
        manifest_version=data.get("manifest_version", "2.0"),
        created_at=data.get("created_at", ""),
        source_platform=data.get("source_platform", "claude-code"),
        source_os=data.get("source_os", ""),
        source_arch=data.get("source_arch", ""),
        source_home=data.get("source_home", ""),
        contents=contents,
        dependencies=dependencies,
    )


def write_manifest(manifest: TransferManifest, path: Path) -> None:
    """Write manifest to a JSON file."""
    data = _manifest_to_dict(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")


def read_manifest(path: Path) -> TransferManifest:
    """Read manifest from a JSON file. Raises ValueError on invalid schema."""
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Invalid manifest at {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Manifest at {path} is not a JSON object")

    return _dict_to_manifest(data)


def read_manifest_from_archive(archive_path: Path) -> Optional[TransferManifest]:
    """Extract and read manifest.json from a tar.gz archive.

    Returns None if no manifest found (legacy archive).
    Uses safe extraction — only reads manifest.json, never extracts to disk.
    """
    try:
        with tarfile.open(str(archive_path), "r:gz") as tf:
            # Look for manifest.json at any level in the archive
            manifest_member = None
            for member in tf.getmembers():
                basename = (
                    member.name.rsplit("/", 1)[-1]
                    if "/" in member.name
                    else member.name
                )
                if basename == "manifest.json" and member.isfile():
                    manifest_member = member
                    break

            if manifest_member is None:
                return None

            # Safe read: extract to memory only, never to disk
            f = tf.extractfile(manifest_member)
            if f is None:
                return None

            raw = f.read().decode("utf-8")
            data = json.loads(raw)
            return _dict_to_manifest(data)

    except (tarfile.TarError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
