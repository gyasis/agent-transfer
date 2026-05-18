"""Destination-side ingestion — read briefing, walk inventory, install per policy.

Implements per-asset conflict resolution (skip / merge / overwrite / ask)
and idempotent merges for ~/.claude.json + settings.json. Calls the
existing rollback generator BEFORE any write so the safety net is in
place.

Constitution:
- R6: paths come from caller / manifest, never hardcoded.
- R7: tarfile extraction goes through safe-extract guard.
- R8: never carry secrets — bundle was already scanned at seal time.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Mapping, Optional

from agent_transfer.bridge.models import AssetEntry, Capability, ManifestModel
from agent_transfer.bridge.rollback import snapshot as _rollback_snapshot
from agent_transfer.bridge.smoke_test import run as _run_smoke


class SettingsCorruptError(RuntimeError):
    """Existing settings.json could not be parsed; refusing to overwrite (C#1)."""


@dataclass
class IngestResult:
    installed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    merged: List[str] = field(default_factory=list)
    declined: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    smoke_failures: List[str] = field(default_factory=list)
    # H (Hunter A F4 / Hunter B G9 adjacent) — set True when an existing
    # rollback.tar.gz from a prior ingest was preserved instead of
    # re-snapshotted. Surfaces the silent-preserve case so the user
    # knows rollback restores the ORIGINAL pre-install state, not the
    # state captured between this ingest and the previous one.
    rollback_reused: bool = False
    # F (Hunter B G1/H2 adjacent) — post-merge re-scan findings.
    # Non-fatal — secrets here may be pre-existing destination state
    # rather than something the bundle introduced. Surface for user
    # visibility instead of blocking install (the seal-time scan
    # already blocked any secret the BUNDLE itself shipped).
    post_merge_secret_warnings: List[str] = field(default_factory=list)


def _ask(prompt: str, *, auto_yes: bool, interactive: bool) -> bool:
    if auto_yes:
        return True
    if not interactive or not sys.stdin.isatty():
        return False
    try:
        ans = input(prompt + " [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans in {"y", "yes"}


def _expand_dest(dest_path: str, home: Path) -> Path:
    if dest_path.startswith("~/"):
        return home / dest_path[2:]
    if dest_path == "~":
        return home
    return Path(dest_path)


def _safe_extract(tar: tarfile.TarFile, target_dir: Path) -> None:
    """Extract a tarfile, rejecting path traversal / abs / symlink escapes (R7)."""
    target_dir = target_dir.resolve()
    for member in tar.getmembers():
        member_path = (target_dir / member.name).resolve()
        if not str(member_path).startswith(str(target_dir) + os.sep) and member_path != target_dir:
            raise RuntimeError(f"Unsafe tar member: {member.name!r}")
        if member.issym() or member.islnk():
            raise RuntimeError(f"Tar contains symlink/hardlink: {member.name!r}")
    tar.extractall(target_dir)


def _sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _merge_json(target_path: Path, incoming: dict) -> None:
    """Idempotent additive merge of incoming dict into target JSON file.

    Used for ~/.claude.json and ~/.claude/settings.json. Keys present in
    BOTH are deep-merged (dict-only). Lists are union'd by canonical
    sort-keyed JSON of items (R12 C#3 fix — robust against dict reorder).
    Existing user values are NEVER replaced.

    R12 C#1 fix: on JSONDecodeError, the existing file is preserved on
    disk (copied to <path>.corrupt-<ts>) and a SettingsCorruptError is
    raised. We never silently wipe user settings.
    """
    existing: dict = {}
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text())
        except json.JSONDecodeError as e:
            from datetime import datetime as _dt
            corrupt_sidecar = target_path.with_suffix(
                target_path.suffix + f".corrupt-{_dt.utcnow().strftime('%Y%m%dT%H%M%S')}"
            )
            corrupt_sidecar.write_bytes(target_path.read_bytes())
            raise SettingsCorruptError(
                f"Could not parse existing {target_path}: {e}. "
                f"Original copied to {corrupt_sidecar}. Refusing to overwrite "
                "user settings — fix the JSON or move it aside and re-ingest."
            ) from e

    def _canonical(item) -> str:
        """Canonical key for list-dedup. Sorts dict keys for stable dedup."""
        try:
            return json.dumps(item, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return repr(item)

    def _merge(a: dict, b: Mapping) -> dict:
        out = dict(a)
        for k, v in b.items():
            if k not in out:
                out[k] = v
            elif isinstance(out[k], dict) and isinstance(v, Mapping):
                out[k] = _merge(out[k], v)
            elif isinstance(out[k], list) and isinstance(v, list):
                seen = {_canonical(x) for x in out[k]}
                for item in v:
                    if _canonical(item) not in seen:
                        out[k].append(item)
                        seen.add(_canonical(item))
            # else: existing user value wins (idempotent)
        return out

    merged = _merge(existing, incoming)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(merged, indent=2))


class _MarkdownMergeError(RuntimeError):
    """Raised when an incoming text fragment can't be section-merged.

    Name kept for backward compat — covers markdown AND shell/python
    section-marker merges (H2).
    """


# Markdown / HTML-comment markers (G1/H8 — CLAUDE.md, skill descriptions).
# `.` is allowed for sub-namespaces (E — `sio.routing` etc.)
_MD_BEGIN_RE = re.compile(r"<!--\s*BEGIN\s+agentbridge:([A-Za-z0-9_\-\.]+)\s*-->")
_MD_END_RE = re.compile(r"<!--\s*END\s+agentbridge:([A-Za-z0-9_\-\.]+)\s*-->")

# Shell / Python / generic-hash-comment markers (H2 — shared hook files).
_SH_BEGIN_RE = re.compile(
    r"^[ \t]*#[ \t]*BEGIN[ \t]+agentbridge:([A-Za-z0-9_\-\.]+)[ \t]*$",
    re.MULTILINE,
)
_SH_END_RE = re.compile(
    r"^[ \t]*#[ \t]*END[ \t]+agentbridge:([A-Za-z0-9_\-\.]+)[ \t]*$",
    re.MULTILINE,
)


def _merge_section(
    target_path: Path,
    incoming_text: str,
    begin_re: "re.Pattern[str]",
    end_re: "re.Pattern[str]",
    *,
    syntax_label: str,
    capability_name: Optional[str] = None,
) -> None:
    """Generic section-marker merge.

    Incoming text MUST contain exactly one BEGIN/END marker pair (matching
    `begin_re` / `end_re`). The block — including markers — replaces any
    same-named block in `target_path`, or is appended if absent.

    Used by:
      • G1/H8 — CLAUDE.md HTML-comment markers
      • H2    — shared shell / python hooks with `# BEGIN agentbridge:<name>`

    Raises _MarkdownMergeError on missing / mismatched / out-of-order markers.

    E (Hunter A F5) — when `capability_name` is provided, the incoming
    marker name MUST equal it OR be a sub-namespace (`<name>.suffix`).
    Without this, a malicious / accidentally-mislabeled bundle for
    capability `sio` could ship a fragment with `agentbridge:cascade-memory`
    markers and silently clobber an unrelated capability's block in the
    same target file.
    """
    begins = list(begin_re.finditer(incoming_text))
    ends = list(end_re.finditer(incoming_text))
    if len(begins) != 1 or len(ends) != 1:
        raise _MarkdownMergeError(
            f"incoming {syntax_label} fragment must contain exactly one "
            f"BEGIN/END agentbridge marker pair "
            f"(found {len(begins)} BEGIN, {len(ends)} END)"
        )
    incoming_name = begins[0].group(1)
    if ends[0].group(1) != incoming_name:
        raise _MarkdownMergeError(
            f"BEGIN name {incoming_name!r} does not match END name "
            f"{ends[0].group(1)!r}"
        )
    if begins[0].start() > ends[0].start():
        raise _MarkdownMergeError("BEGIN marker appears after END marker")

    # E — bind marker name to capability name (or sub-namespace).
    if capability_name is not None:
        if not (
            incoming_name == capability_name
            or incoming_name.startswith(capability_name + ".")
        ):
            raise _MarkdownMergeError(
                f"section marker {incoming_name!r} does not belong to "
                f"capability {capability_name!r}; expected {capability_name!r} "
                f"or {capability_name + '.<sub>'!r}. Refusing to clobber a "
                "different capability's block."
            )

    existing = target_path.read_text()
    name_re = re.escape(incoming_name)

    # Build a per-syntax block-matching regex by re-using the marker regex
    # patterns with the captured name pinned in.
    if syntax_label == "markdown":
        block_re = re.compile(
            r"<!--\s*BEGIN\s+agentbridge:" + name_re + r"\s*-->"
            r".*?"
            r"<!--\s*END\s+agentbridge:" + name_re + r"\s*-->",
            re.DOTALL,
        )
    else:  # shell/python
        block_re = re.compile(
            r"^[ \t]*#[ \t]*BEGIN[ \t]+agentbridge:" + name_re + r"[ \t]*$"
            r".*?"
            r"^[ \t]*#[ \t]*END[ \t]+agentbridge:" + name_re + r"[ \t]*$",
            re.DOTALL | re.MULTILINE,
        )

    incoming_block = incoming_text[begins[0].start():ends[0].end()]

    if block_re.search(existing):
        new_text = block_re.sub(lambda _m: incoming_block, existing, count=1)
    else:
        sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
        new_text = existing + sep + incoming_block + "\n"

    target_path.write_text(new_text)


def _merge_markdown(
    target_path: Path,
    incoming_text: str,
    capability_name: Optional[str] = None,
) -> None:
    """G1/H8 wrapper — preserved for callers that import it directly."""
    _merge_section(
        target_path, incoming_text, _MD_BEGIN_RE, _MD_END_RE,
        syntax_label="markdown",
        capability_name=capability_name,
    )


def _merge_shell(
    target_path: Path,
    incoming_text: str,
    capability_name: Optional[str] = None,
) -> None:
    """H2 wrapper — section-marker merge for shell / python hooks."""
    _merge_section(
        target_path, incoming_text, _SH_BEGIN_RE, _SH_END_RE,
        syntax_label="shell",
        capability_name=capability_name,
    )


def _post_merge_secret_scan(target_path: Path) -> List[str]:
    """F (Hunter B G1/H2 adjacent) — re-scan the merged file for secrets.

    The seal-time scanner runs on every asset BYTE the bundle ships, so
    secrets the bundle itself contains are blocked at compose time. But
    after a merge, the on-disk file is `existing_destination + our_block`.
    A pre-existing destination block could contain credentials we just
    extended (or chained into) by appending. Re-scan the result and
    return human-readable warnings; non-fatal because the secret may
    be entirely pre-existing — out of AgentBridge's control to remove.
    """
    from agent_transfer.bridge.secrets import scan as _scan
    try:
        text = target_path.read_text(errors="replace")
    except OSError:
        return []
    findings = _scan(text)
    if not findings:
        return []
    return [
        f"post-merge secret in {target_path}: {f.pattern} {f.match[:24]}…"
        for f in findings[:5]
    ]


def _open_bundle(bundle_path: Path) -> Path:
    """Bundle can be a directory or a .tar.gz. Returns path to the dir."""
    if bundle_path.is_dir():
        return bundle_path
    if bundle_path.suffix in {".gz", ".tgz"} or str(bundle_path).endswith(".tar.gz"):
        target = bundle_path.parent / (bundle_path.stem.replace(".tar", "") + "-extracted")
        target.mkdir(exist_ok=True)
        with tarfile.open(bundle_path, "r:gz") as tar:
            _safe_extract(tar, target)
        return target
    raise ValueError(f"Bundle must be a directory or .tar.gz: {bundle_path}")


def _apply_one_asset(
    asset: AssetEntry,
    bundle_dir: Path,
    home: Path,
    *,
    auto_yes: bool,
    interactive: bool,
    result: IngestResult,
    capability_name: Optional[str] = None,
) -> None:
    src = bundle_dir / "bundle" / asset.path
    if not src.exists():
        result.errors.append(f"Bundle missing asset bytes for {asset.path}")
        return

    # Verify hash before install (corruption / tampering check)
    actual = _sha256_of(src)
    if actual != asset.sha256:
        result.errors.append(
            f"sha256 mismatch on bundle asset {asset.path}: expected {asset.sha256[:12]}…, got {actual[:12]}…"
        )
        return

    dest = _expand_dest(asset.dest_path, home)

    # Risk gate
    if asset.risk in ("yellow", "red"):
        ok = _ask(
            f"Install {asset.risk.upper()} asset {asset.dest_path}?",
            auto_yes=auto_yes, interactive=interactive,
        )
        if not ok:
            result.declined.append(asset.dest_path)
            return

    # Conflict policy
    policy = asset.conflict
    if dest.exists() and policy == "skip":
        result.skipped.append(asset.dest_path)
        return
    if dest.exists() and policy == "ask":
        ok = _ask(f"Overwrite existing {asset.dest_path}?", auto_yes=auto_yes, interactive=interactive)
        if not ok:
            result.skipped.append(asset.dest_path)
            return

    if policy == "merge" and dest.exists() and dest.suffix == ".json":
        try:
            incoming = json.loads(src.read_text())
        except json.JSONDecodeError:
            result.errors.append(f"merge requested for non-JSON file {asset.path}")
            return
        try:
            _merge_json(dest, incoming)
        except SettingsCorruptError as e:
            # R12 C#1 — refuse to wipe; surface to user, don't silently destroy.
            result.errors.append(str(e))
            return
        result.merged.append(asset.dest_path)
        # J — post-merge scan also applies to JSON merge. ~/.claude.json
        # and settings.json are exactly where Bearer/api-key tokens are
        # most likely to land via mcpServers env vars; not scanning them
        # was the most damaging gap of the 8-fix pass (Hunter A N4).
        result.post_merge_secret_warnings.extend(_post_merge_secret_scan(dest))
    elif policy == "merge" and dest.exists() and dest.suffix == ".md":
        # G1/H8 — section-marker merge for markdown (CLAUDE.md fragments).
        # Bundle ships a fragment wrapped in <!-- BEGIN agentbridge:<name> -->
        # … <!-- END agentbridge:<name> --> markers; merge replaces the
        # existing block with that name (idempotent re-ingest) or appends
        # if absent. Anything outside markers in the destination file is
        # preserved untouched.
        try:
            _merge_markdown(dest, src.read_text(), capability_name=capability_name)
        except _MarkdownMergeError as e:
            result.errors.append(f"markdown merge failed for {asset.path}: {e}")
            return
        result.merged.append(asset.dest_path)
        result.post_merge_secret_warnings.extend(_post_merge_secret_scan(dest))
    elif policy == "merge" and dest.exists() and dest.suffix in (".sh", ".py", ".bash", ".zsh"):
        # H2 — section-marker merge for shared shell/python hooks.
        # Hook files like ~/.claude/hooks/session-start.sh are co-owned by
        # multiple capabilities (memory + retry-guard + sio + specstory).
        # Whole-file overwrite would clobber peers; section-marker merge
        # extracts/inserts only the named block.
        try:
            _merge_shell(dest, src.read_text(), capability_name=capability_name)
        except _MarkdownMergeError as e:
            result.errors.append(f"shell hook merge failed for {asset.path}: {e}")
            return
        result.merged.append(asset.dest_path)
        result.post_merge_secret_warnings.extend(_post_merge_secret_scan(dest))
    else:
        # R12 H#7 — guard against degenerate mode_bits values.
        mode = _safe_mode_bits(asset.dest_path, asset.mode_bits)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Use os.open to atomically write with mode (closes H#7 race).
        with open(src, "rb") as fin:
            data = fin.read()
        fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        os.chmod(dest, mode)  # FR-011 — preserve executable bit
        # Preserve mtime from bundle for deterministic round-trip.
        try:
            st = os.stat(src)
            os.utime(dest, (st.st_atime, st.st_mtime))
        except OSError:
            pass
        result.installed.append(asset.dest_path)
        # J — post-merge scan also applies to overwrite path. The seal-
        # time scanner is best-effort, and a regex miss on the bundle
        # source means the secret rides through. Re-scanning post-write
        # gives a second chance with a tiny amount of work (Hunter A N5).
        result.post_merge_secret_warnings.extend(_post_merge_secret_scan(dest))


# ----------------------------------------------------------------------
# R12 H#7 — mode_bits sanity check
# ----------------------------------------------------------------------


def _safe_mode_bits(dest_path: str, mode_bits: int) -> int:
    """Clamp mode_bits to a sane minimum; force exec bit on hooks/bin scripts.

    Per adversarial finding: a bundled asset with mode_bits == 0 (e.g. NTFS
    source where exec bit isn't stored) would write a 0o000 file and silently
    break ingestion. Clamp to 0o400 minimum, and force 0o755 for any path
    under ~/.claude/hooks/ or ~/bin/ or ~/.local/bin/ that would otherwise
    lack the executable bit.
    """
    m = int(mode_bits) if mode_bits and mode_bits > 0 else 0o644
    # Always at least owner-readable.
    m |= 0o400
    is_hook = "/.claude/hooks/" in dest_path
    is_bin = "/bin/" in dest_path
    if is_hook or is_bin:
        m |= 0o100  # owner exec; preserve any group/other bits already set
    return m & 0o7777


def ingest(
    bundle_path: Path,
    *,
    home: Optional[Path] = None,
    auto_yes: bool = False,
    interactive: bool = True,
    skip_smoke_commands: bool = False,
) -> IngestResult:
    """Install an AgentBridge bundle on this machine.

    Args:
        bundle_path: Either a bundle directory or a .tar.gz file.
        home: Override $HOME (for tests with sandbox HOME).
        auto_yes: Skip prompts; treat all Yellow/Red as confirmed.
        interactive: Allow stdin prompts; otherwise behave as auto-no.

    Returns:
        IngestResult with installed / skipped / merged / declined / errors
        / smoke_failures lists.
    """
    home = home or Path.home()
    bundle_dir = _open_bundle(Path(bundle_path))
    result = IngestResult()

    # Read manifest
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        result.errors.append(f"Bundle missing manifest.json at {manifest_path}")
        return result

    # v1.1 — pre-parse the manifest JSON so we can:
    #   • reject schema_version 2.x BEFORE pydantic sees it (clearer error)
    #   • back-compat 1.0.x bundles whose AssetEntry rows have no `kind`
    #     field — infer it from dest_path via _infer_kind_from_dest so the
    #     v1.1 ManifestModel can validate.
    import json
    import warnings as _warnings

    try:
        raw_manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        result.errors.append(f"manifest.json is not valid JSON: {e}")
        return result

    raw_schema_version = str(raw_manifest.get("schema_version", "1.0.0"))
    major = raw_schema_version.split(".", 1)[0]
    if major != "1":
        result.errors.append(
            f"Bundle schema_version {raw_schema_version} is not 1.x — refusing. "
            f"This ingest expects 1.0.x (back-compat) or 1.1.x. Major version "
            f"bumps (2.x+) indicate breaking schema changes; upgrade "
            f"agent-transfer or downgrade the producer."
        )
        return result

    minor = raw_schema_version.split(".")[1] if "." in raw_schema_version else "0"
    if minor == "0":
        from agent_transfer.utils.config_manager import _infer_kind_from_dest

        _warnings.warn(
            (
                f"Ingesting legacy schema_version={raw_schema_version} bundle. "
                "AssetEntry.kind will be inferred from dest_path. Upgrade the "
                "producer to v1.1+ for explicit kind classification."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            assets = raw_manifest.get("capability", {}).get("assets", []) or []
            for a in assets:
                if "kind" not in a:
                    a["kind"] = _infer_kind_from_dest(a.get("dest_path", ""))
        except Exception:
            # Defensive — if the shape is unexpected pydantic will error
            # below with a clearer message than we'd produce ad-hoc.
            pass

    try:
        manifest = ManifestModel.model_validate(raw_manifest)
    except Exception as e:  # pragma: no cover — pydantic raises ValidationError
        result.errors.append(f"manifest.json failed validation: {e}")
        return result

    # Generate rollback snapshot BEFORE any write (FR-016).
    # H — flag whether the existing rollback.tar.gz was preserved (G9
    # baseline-protect path) so the user can be told they're re-ingesting.
    target_dest_paths = [a.dest_path for a in manifest.capability.assets]
    rollback_tar_path = bundle_dir / "rollback.tar.gz"
    result.rollback_reused = rollback_tar_path.exists()
    _rollback_snapshot(target_dest_paths, bundle_dir, home=home)

    # Apply each asset
    for asset in manifest.capability.assets:
        _apply_one_asset(
            asset, bundle_dir, home,
            auto_yes=auto_yes, interactive=interactive, result=result,
            capability_name=manifest.capability.name,
        )

    # Smoke test (FR-017). D — `skip_smoke_commands` lets the receiver
    # opt out of capability-declared `sh -c` execution while keeping
    # presence + sha + dep checks.
    smoke = _run_smoke(
        manifest, home=home, skip_smoke_commands=skip_smoke_commands
    )
    if not smoke.passed:
        result.smoke_failures = smoke.failures

    return result
