# Feature Specification: AgentBridge v1.2 — MCP Co-Located Source Bundling

**Feature Branch**: `005-mcp-colocated-source`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "MCP servers wrapped in FastMCP-style libraries and exposed to Claude Code via local SSE/HTTP URLs hide their source from the classifier. The mcpServers entry is just `{type: sse, url: 127.0.0.1:<port>}` — there is no command, no path, no way for `mcp_classifier` to know that a docker-compose project at `~/dev/<repo>/` is what serves that URL locally. Add an explicit user-declared link so AgentBridge can bundle the source repo + launch recipe + health probe alongside the URL entry."
**Predecessor**: feature 003 (`AgentBridge MVP`) shipped via merge `74ccac1` to master 2026-05-05. Independent of feature 004 (`mac-compat`).
**Canonical example**: `deeplake-rag` MCP at `~/dev/deepcloud/deepmcp/` (FastMCP + docker compose + SSE on 127.0.0.1:8767).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Bundle a docker-hosted FastMCP server reachable via local SSE (Priority: P1) — SHIP GATE

A user has a working MCP server defined as a docker-compose project on the source machine. The container exposes a FastMCP-driven SSE endpoint at `http://127.0.0.1:<port>/sse`. Claude Code reaches it via `~/.claude.json` → `mcpServers.<name>` → `{type: "sse", url: "http://127.0.0.1:<port>/sse"}`. The source code (Dockerfile + docker-compose.yml + Python module + `.env.example`) lives at a known path under `$HOME` (e.g. `~/dev/deepcloud/deepmcp/`).

Today (post-003), `ab compose --capability <name>` classifies this entry as `CLASS_HTTP` / `CAPTURE_RECORD_URL` / `REWRITE_NONE`. The bundle records only the URL. Destination has nothing listening at `127.0.0.1:<port>` and the MCP fails on first invocation.

Story 1 makes the user's `mcpServers.<name>` entry carry an explicit AgentBridge sidecar that names the local source directory. The classifier reroutes those entries to a new `local-http-source` class, the existing `mcp_source_bundler` tars the source dir into `mcp-sources/<name>.tar.gz`, the BRIEFING records the launch recipe + health probe, and ingestion extracts → launches → probes the URL before declaring success.

**Why this priority**: This is the v1.2 ship gate and the smallest scope that delivers the actual user need. Without it, any MCP that uses the `mcp[cli]` Python library (FastMCP) and is hosted locally cannot be transferred at all — the URL is recorded but the server it points at is left behind. This is a strictly additive change; existing classifications continue unchanged.

**Independent Test**: On the source machine, given `~/.claude.json` with `mcpServers.deeplake-rag = {type: sse, url: "http://127.0.0.1:8767/sse", _agent_transfer: {source_dir: "~/dev/deepcloud/deepmcp", launch_recipe: "docker_compose", health_check_url: "http://127.0.0.1:8767/sse"}}`, running `ab compose --capability deeplake-rag` produces a bundle whose `mcp-sources/deeplake-rag.tar.gz` contains the source tree (excluding `.env`, `__pycache__`, `.git`) and whose manifest records the launch recipe + health probe. Running `ab ingest <bundle>` on a fresh sandbox HOME extracts the tarball, prompts for `.env` values from the bundled `.env.example`, runs `docker compose up -d` from the extracted dir, and probes the health URL until 200-OK before applying conflict policy on the `~/.claude.json` entry.

**Acceptance Scenarios**:

1. **Given** an `mcpServers` entry with a `_agent_transfer.source_dir` sidecar pointing at an existing directory under `$HOME`, **When** `ab compose --capability <name>` runs, **Then** the classifier emits `server_class="local-http-source"`, `capture_strategy="bundle-source"`, and the existing `mcp_source_bundler.bundle_mcp_sources()` produces `mcp-sources/<name>.tar.gz` with the standard exclusions (`.venv`, `node_modules`, `__pycache__`, `.git`, `*.pyc`, `*.log`).
2. **Given** the bundled source dir contains a `.env` file with secrets, **When** the source bundler runs, **Then** `.env` is excluded from the tarball BUT `.env.example` (if present) is included, and the manifest records `secrets_redacted: true` for that entry. If `.env.example` is absent, the bundler synthesizes one by reading `.env` keys and emitting `<KEY>=` (no values) to the tarball.
3. **Given** an `mcpServers` entry tagged `launch_recipe: "docker_compose"`, **When** ingestion runs, **Then** install steps include extracting the tarball to `$HOME/<rel-path>`, sourcing the destination-supplied `.env`, running `docker compose up -d` from the extracted dir, and polling `health_check_url` for HTTP 200 (timeout 60s, configurable). Failure of any step aborts ingestion and triggers `rollback.sh`.
4. **Given** an `mcpServers` entry without `_agent_transfer` sidecar, **When** the classifier runs, **Then** it falls through to the existing `CLASS_HTTP` / `CAPTURE_RECORD_URL` path with no behaviour change. Story 1 must not regress existing HTTP/SSE classification.
5. **Given** the `_agent_transfer.source_dir` does not exist or is outside `$HOME`, **When** the classifier runs, **Then** it emits a Yellow warning and falls back to `CAPTURE_RECORD_URL` (do not silently bundle from outside `$HOME`).

---

### User Story 2 — Bare `uv run` MCP server with co-located SSE (Priority: P2)

A user has an MCP server launched directly via `uv run` (no docker) that internally calls `mcp.run(transport="sse")` and binds a local port — e.g. graphiti-mcp shape, but exposed via SSE rather than stdio. The `mcpServers` entry shape is identical to Story 1 (`{type: sse, url: ...}`) but the launch recipe is different: instead of `docker compose up -d`, it's `uv run --directory <dir> python main.py --transport sse --port <port>`.

Story 2 generalizes Story 1's `launch_recipe` field: in addition to `"docker_compose"`, accept `"uv_run"` and `"shell_command"`. The classifier and source bundler do not change; only the ingestion install-steps generator branches on the recipe.

**Why this priority**: Multiple user MCPs (graphiti, gemini) follow this shape. Adding it costs almost nothing once Story 1 lands — same classifier change, same bundler, only the ingest install-steps generator gains 2 new cases. Doing both in one v1.2 ship is cheaper than splitting.

**Independent Test**: Given a fixture `mcpServers` entry with `_agent_transfer: {source_dir, launch_recipe: "uv_run", launch_args: ["--port", "8766"]}`, the bundle's manifest records the recipe and the BRIEFING's install steps include `cd $HOME/<rel-path> && uv sync && uv run python main.py --transport sse --port 8766 &` (background-launch syntax TBD).

**Acceptance Scenarios**:

1. **Given** `launch_recipe: "uv_run"` with `launch_args: [...]`, **When** ingest runs, **Then** install steps include `uv sync` followed by `uv run python <entrypoint> <launch_args>` as a backgrounded process (with PID file written to `$HOME/.cache/agent-transfer/<name>.pid` so rollback can stop it).
2. **Given** `launch_recipe: "shell_command"` with `launch_command: "<arbitrary string>"`, **When** ingest runs, **Then** the BRIEFING surfaces the command as Red-tier (arbitrary shell) and prompts the user Y/N before execution. Sidecar value is recorded verbatim with no shell escaping.
3. **Given** any of the three recipe types, **When** post-launch health probe fails, **Then** ingest aborts and the launched process (PID file or `docker compose down`) is torn down by rollback.

---

### User Story 3 — Source-side manifest as fallback when `~/.claude.json` should not carry sidecar (Priority: P3)

Some users do not want to pollute `~/.claude.json` with `_agent_transfer` keys (machine-specific, may be overwritten by config-management tooling, or shared across MCP clients). For those users, accept a `.agent-transfer.yml` manifest in the source dir itself, declaring "I back the `<name>` MCP." On compose, after exhausting the sidecar path, the classifier scans candidate source dirs — those declared by `~/.config/agent-transfer/source-roots.yml` — for a matching manifest.

**Why this priority**: Usability nicety, not a correctness gap. Stories 1+2 deliver the full feature; Story 3 lets users choose where the link metadata lives. P3 because the sidecar path covers the canonical case. Defer if implementation pressure is high.

**Independent Test**: Given `~/.config/agent-transfer/source-roots.yml` listing `~/dev/deepcloud/deepmcp/` and that dir containing `.agent-transfer.yml: {mcp_name: "deeplake-rag", launch_recipe: "docker_compose", health_check_url: "..."}`, `ab compose --capability deeplake-rag` produces the same bundle as Story 1 even when `~/.claude.json` contains no sidecar.

**Acceptance Scenarios**:

1. **Given** no sidecar in `~/.claude.json` and a valid `.agent-transfer.yml` in a source-root-listed directory, **When** compose runs, **Then** the resolved metadata is identical to the sidecar path (Story 1 P1).
2. **Given** both a sidecar AND a source-side manifest, **When** compose runs, **Then** the sidecar wins and a Yellow warning notes the duplicate.
3. **Given** a source-side manifest in a directory NOT listed in `source-roots.yml`, **When** compose runs, **Then** the manifest is ignored (do not auto-discover from arbitrary paths — security boundary).

---

## Requirements *(functional)*

### FR-005-01 — `_agent_transfer` sidecar schema in `mcpServers` entry

The `_agent_transfer` field is an optional dict on any `mcpServers.<name>` entry. Recognised keys:

| Key | Type | Required | Notes |
|---|---|---|---|
| `source_dir` | str (path under `$HOME`) | yes | Tilde-expanded; rejected if outside `$HOME` |
| `launch_recipe` | enum: `docker_compose` \| `uv_run` \| `shell_command` | yes | Drives ingest install-steps generation |
| `launch_args` | list[str] | no (default `[]`) | Recipe-specific args |
| `launch_command` | str | required iff `launch_recipe == "shell_command"` | Verbatim shell string, Red-tier |
| `health_check_url` | str | yes | Absolute URL; ingest probes until 200 |
| `health_check_timeout_s` | int | no (default 60) | |

Unknown keys: ignored with warning (forward-compat).

### FR-005-02 — New classifier class `local-http-source`

`mcp_classifier._classify_entry` adds one branch BEFORE the existing `CLASS_HTTP` branch (lines 149–158): if `cfg.get("_agent_transfer", {}).get("source_dir")` is set AND the path resolves under `$HOME` AND exists, set `server_class="local-http-source"`, `capture_strategy="bundle-source"`, `rewrite_strategy="rewrite-home"`. Otherwise fall through to existing HTTP path. No other classifier paths change.

### FR-005-03 — Source bundler reuse, `.env` redaction

`mcp_source_bundler.bundle_mcp_sources` is unchanged at the function signature level. The exclude list grows by `.env`, `.env.local`, `.env.*.local`. If `.env` exists in source AND `.env.example` does not, synthesize an `.env.example` containing the keys (no values) and inject it into the tarball at the same relpath.

### FR-005-04 — BRIEFING.md MCP install steps

Section 4 (Build Instructions) and Section 5 (Ingest Instructions) of the BRIEFING gain per-entry install steps for `local-http-source` servers, recipe-aware. Section 6 (Verification) gains an explicit "health probe each `local-http-source` URL within timeout" step.

### FR-005-05 — Ingest health probe + teardown linkage

`ab ingest` runs the recipe-specific launch step, polls `health_check_url`, and on failure invokes `rollback.sh` which must know how to tear down each launched MCP (compose down OR PID-file-kill). Rollback metadata records the recipe and any PIDs so rollback is idempotent.

### FR-005-06 — Out-of-scope path is rejected, not silently bundled

If `source_dir` resolves outside `$HOME`, the classifier records a Yellow warning, falls back to `CAPTURE_RECORD_URL`, and the bundle records `_agent_transfer_skipped: "source_dir outside HOME"` for transparency. The ingest BRIEFING surfaces this so the user knows the URL is recorded but the source is not bundled.

### FR-005-07 — Backwards compatibility

Existing bundles produced by 003 with no `_agent_transfer` keys must compose and ingest identically. All sidecar logic is gated on the presence of the sidecar key. Schema version bumps from 1.0.0 to **1.1.0** (additive, minor).

## Out of Scope (v1.2)

- Stdio-transport MCPs whose entry already has a `command` (existing `local-uv`, `local-python`, `local-node` paths handle these — unchanged).
- Auto-detection of source dirs without a sidecar or source-root manifest. We will NOT scan `~/dev/` for `Dockerfile + docker-compose.yml + main.py` shapes.
- Cross-platform path rewriting beyond what 003 already does (Linux→Mac is feature 004's job).
- Alternative MCP transports (websocket, streamable-http) — same shape as SSE for v1.2 purposes; supported transparently because the classifier reads `cfg.type` only to confirm it's a known HTTP-class transport.
- Multi-MCP-per-capability dep-graph auto-resolution (manifest can list multiple MCPs explicitly; auto-detection from skill/rule body deferred).

## Success Criteria

- **SC-005-01** — `deeplake-rag` round-trip on a fresh sandbox HOME succeeds end-to-end: compose → ship bundle → ingest → probe SSE URL → tool call returns 200. No manual intervention beyond pasting `.env` values.
- **SC-005-02** — Backwards-compat: every existing 003 fixture bundle composes and ingests with byte-identical manifests (modulo `schema_version` bump).
- **SC-005-03** — Secrets in `.env` never appear in the bundle. Verified by post-seal scan of the tarball + manifest for known secret patterns (extends existing `secrets.py` scan to walk `mcp-sources/*.tar.gz` contents).
- **SC-005-04** — Health-probe failure → rollback restores pre-install state with zero leftover containers, processes, or files. Verified by file-tree diff + `docker ps` + PID-file absence.
- **SC-005-05** — Rejection paths (source outside `$HOME`, missing entrypoint, malformed sidecar) emit clear Yellow warnings and fall back to URL-only recording — they do not silently produce broken bundles.

## Open Questions

1. **PID file location** — `$HOME/.cache/agent-transfer/<name>.pid` vs `/var/run/user/$UID/...` vs source-dir-local. Pick before implementation.
2. **Health probe protocol** — `curl -sSf <url>` is the obvious default, but FastMCP's SSE endpoint at `/sse` doesn't return 200 on idle GET (it streams). Need a probe that confirms server is up without consuming the SSE stream. Likely a separate `/health` endpoint or a HEAD on the base URL — investigate during implementation.
3. **`_agent_transfer` key namespace** — Claude Code today ignores unknown keys in `mcpServers` entries; verify this stays true across upcoming Claude Code versions, or use a more obscure prefix like `x-agent-transfer`.
4. **docker compose vs docker-compose** — modern Docker uses `docker compose` (subcommand); older installs have `docker-compose` (separate binary). Ingest must detect and use whichever is on PATH, or fail-closed with a clear error.

## Implementation Notes (non-normative)

- Touchpoints: `agent_transfer/utils/mcp_classifier.py` (new branch), `agent_transfer/utils/mcp_source_bundler.py` (exclude list + `.env.example` synthesis), `agent_transfer/bridge/compose.py` (manifest field plumbing), `agent_transfer/bridge/ingest.py` (recipe-aware install steps + health probe), `agent_transfer/bridge/rollback.py` (teardown-aware), `agent_transfer/bridge/secrets.py` (scan inside tarballs), BRIEFING template, manifest schema (v1.1.0).
- New tests: `tests/contract/test_mcp_local_http_source.py`, `tests/integration/test_deeplake_round_trip.py` (canonical example), extend `tests/integration/test_path_rewrite_mcp.py`.
- Estimated size: ~400-600 LOC across the three modules, plus tests.
