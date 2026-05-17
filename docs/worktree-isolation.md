# Subagent Worktree Isolation — What Works, What Doesn't

When this repo's contributors spawn Claude Code subagents with
`isolation: "worktree"`, the runtime creates a fresh `git worktree` at
`.claude/worktrees/agent-<hash>/`, checks out a `worktree-agent-<hash>`
branch from current HEAD, and runs the agent inside that tree.

This page documents what subagents CAN and CANNOT see inside a
worktree, and which task patterns are safe vs. unsafe.

## What a worktree subagent CAN reach

- The full repo tree at HEAD of master (all tracked files)
- The shared `.git/` directory (linked back to the parent repo)
- Environment variables of the parent shell
- Standard Python/Node toolchains on PATH
- The repo's pytest suite (`python -m pytest -x -q` works)

## What a worktree subagent CANNOT reach

- **`~/dev/prd/scratch/*.md`** — PRD files outside the repo are sandbox-blocked
- **`~/.claude/rules/`, `~/.claude/projects/.../memory/`** — host-side Claude config
- **`.memory/active-prds.json`** in the parent repo
- **Sibling worktrees** at other `.claude/worktrees/agent-*/` paths
- **Gitignored content** in the parent — `.claude/`, `memory-bank/private/`,
  `CLAUDE.md`, `.specstory/` — none of this propagates to a fresh `git worktree add`

## Task patterns

### Worktree-safe ✅

- Pure code edits where the spec lives **in the repo** (e.g. under `specs/`,
  in a tracked PRD, or in a tracked Markdown design doc)
- Test-driven work — pytest runs fine inside the worktree
- Anything whose context fits inline in the spawn prompt

### Worktree-unsafe ❌

- "Read PRD at `/home/user/dev/prd/scratch/foo.md` then implement" — the agent
  can't see the file. **Either copy the PRD into the repo as a tracked spec
  doc, or paste its body into the spawn prompt.**
- Tasks that need `~/.claude/rules/` content
- Tasks that need to read `.memory/active-prds.json` or other gitignored
  state in the parent

## Parallel-feature patterns

When you need TWO subagents working at the same time on different
features in this repo:

| Pattern | When |
|---|---|
| **Worktree isolation** | Both tasks are worktree-safe AND they edit overlapping files |
| **Same repo, file-partition** | Tasks edit disjoint files; spawning agent acts as merge chairman for any shared file (e.g. `cli.py`) |
| **Separate clones** (`/tmp/clone-A`, `/tmp/clone-B`) | Tasks need outside-repo context AND have file overlap; manual merge at end |
| **Sequential** | Tasks are interdependent (B uses A's new API) |

## Hygiene

Subagents that fail (timeout, denied permission, agent bail) leak
worktrees + branches. Run periodically:

```bash
bash scripts/worktree-clean.sh             # remove dead-pid worktrees + orphan branches
bash scripts/worktree-clean.sh --dry-run   # preview without changes
```

The janitor refuses to touch worktrees whose lock pid is still alive,
so it's safe to run anytime.

## Hook dependency

A fresh worktree fires `.git/hooks/post-checkout`, which symlinks
`memory-bank/shared/.constitution.md` → `.specify/memory/constitution.md`.
This hook is version-controlled at `scripts/hooks/post-checkout` and
installed via `git config core.hooksPath scripts/hooks` in `install.sh`.

If subagents report constitution-link errors:
1. Confirm `git config --get core.hooksPath` returns `scripts/hooks`
2. Confirm `.specify/memory/constitution.md` is tracked and present
3. Confirm `memory-bank/shared/` exists in the worktree (the hook
   creates it via `mkdir -p`, but pre-2026-05-17 hooks did not)

## Why worktrees live inside `.claude/worktrees/`

This is a Claude Code runtime decision, not a repo decision. The
`.gitignore` covers `/.claude/worktrees/` explicitly so nested worktree
trees never accidentally get staged. The placement is sub-optimal but
not currently configurable from this side.
