# Data Model — AgentBridge MVP (003)

Authoritative reference for the Pydantic models in
`agent_transfer/bridge/models.py`. The on-disk JSON Schema at
`contracts/manifest.schema.json` is the wire-format contract; this
document is its prose companion.

## Type primitives

```python
RiskTag             = Literal["green", "yellow", "red"]
ConflictPolicy      = Literal["skip", "merge", "overwrite", "ask"]
BriefingSectionName = Literal[
    "identity",
    "capability_description",
    "inventory",
    "build_instructions",
    "ingest_instructions",
    "verification",
    "rollback",
]
```

The 7 `BriefingSectionName` values are the **mandatory** sections of every
rendered `BRIEFING.md` (FR-007). The contract test in
`tests/contract/test_briefing_sections.py` enforces this.

## `AssetEntry`

| Field | Type | Notes |
|---|---|---|
| `path` | `str` | Path inside the bundle (relative to `bundle/`). |
| `dest_path` | `str` | Destination on the receiver. `~` is expanded at ingest time, not at composition time. |
| `risk` | `RiskTag` | Drives whether ingest prompts the user. |
| `conflict` | `ConflictPolicy` | What to do when destination has a file. |
| `sha256` | `str` | 64-char hex digest of the bundled bytes. Verified on ingest. |
| `mode_bits` | `int ≥ 0` | POSIX mode bits to restore on ingest. Executable bit must survive (FR-011). |
| `notes` | `Optional[str]` | Human-readable note shown in Briefing Preview. |

**Why `dest_path` is a string, not `Path`**: the manifest serializes to
JSON. Storing as `str` keeps the wire format independent of Python's
`PurePosixPath`/`PureWindowsPath` ambiguity (we're Linux/WSL only per R3,
but the schema is portable).

## `BriefingSection`

| Field | Type | Notes |
|---|---|---|
| `name` | `BriefingSectionName` | One of the 7 mandatory section IDs. |
| `content_md` | `str` | Rendered Markdown. |

The receiving Claude reads briefing sections in the order they appear
in `manifest.briefing_sections`. The renderer (T028) preserves the
template's section order.

## `Capability`

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | User-facing capability name, e.g. `"cascade-memory"`. |
| `description` | `str` | One-sentence what-it-does. |
| `intent` | `str` | Why-it-exists, in the user's words where possible. |
| `assets` | `List[AssetEntry]` | Concrete files. May be empty for under-construction bundles but ship-time bundles MUST be non-empty. |
| `dependencies` | `List[str]` | OS-level binary names the destination must have on PATH (e.g. `"ripgrep"`). NOT Python deps — Python deps come via `pyproject.toml`. |

## `Confirmation`

| Field | Type | Notes |
|---|---|---|
| `asset_path` | `str` | Matches an `AssetEntry.dest_path`. |
| `risk` | `RiskTag` | Risk at the moment of confirmation. |
| `decided_at` | `datetime` | When the user pressed Y/N. |
| `user_choice` | `Literal["yes", "no"]` | Decision. |

`Confirmation` records are appended in order of the source-side
Briefing Preview UI. They're shipped in the bundle for SC-007 audit. The
ingest side can choose to honor them implicitly (skip re-confirmation
on Yellow that was already approved) or always re-prompt (default v1
behavior to keep the flow simple).

## `ManifestModel`

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `str` | Currently `"1.0.0"`. Bump on breaking shape changes. |
| `generated_at` | `datetime` | UTC timestamp at seal. |
| `source_machine_hint` | `str` | Non-identifying — e.g. `"linux-wsl2-claude-code-v2.x"`. Never carry hostname or username. |
| `capability` | `Capability` | The bundle's payload. |
| `briefing_sections` | `List[BriefingSection]` | Renderer's output, embedded for traceability. |
| `confirmations` | `List[Confirmation]` | User Y/N decisions captured pre-seal. |

## Design choices

### Why "capabilities, not files"

The unit of work is the named **capability** (e.g. cascade-memory), not a
flat file list. Two implications:

1. The composer (T026) infers contributing assets from a capability
   name via dependency-graph walk. It does NOT take a file list as input.
2. The receiving side recomposes the capability semantically. If the user
   trims a COMPANIONS asset at ingest time, the smoke test still passes
   as long as CORE assets are intact.

### Why `dest_path` is the join key

Not `path`. The bundle's internal layout (under `bundle/`) is an
implementation detail; the destination path is what determines whether
two bundles conflict. Two different bundles writing to the same
`dest_path` is a conflict the user must resolve, regardless of how each
laid out its internal `path`.

### Why `mode_bits` is mandatory

A `~/bin/<x>` script that loses its executable bit is a silent failure on
ingest — the script appears to be installed but the agent can't invoke
it. Capturing `mode_bits` and restoring it is the cheap fix; an
integration test (T037 / SC-001 step 5) verifies this.

### Why `sha256` is mandatory

Two reasons: (1) corruption detection on ingest — a bundle that's
been edited in-flight is a security concern. (2) Determinism for
SC-002 — the rollback file-tree diff compares hashes, not just
presence.

### Schema versioning policy

`schema_version` is SemVer. **Major** bump = breaking shape change
(field removed, type changed, new required field). **Minor** = additive
optional field. **Patch** = clarification only. v1 ships at `1.0.0`.

The receiving `agentbridge-ingest` skill MUST refuse bundles whose
major version it does not recognize. v1 only recognizes `1.x.x`.

## Cross-references

- Pydantic source: `agent_transfer/bridge/models.py`
- JSON Schema contract: `specs/003-agentbridge-mvp/contracts/manifest.schema.json`
- Briefing template: `specs/003-agentbridge-mvp/contracts/briefing.template.md`
- Round-trip test: `tests/contract/test_manifest_schema.py` (T017)
- Ingest consumer: `agent_transfer/bridge/ingest.py` (T033, Wave 5)
- Composer producer: `agent_transfer/bridge/compose.py` (T026, Wave 3)
