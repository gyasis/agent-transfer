#!/bin/bash
# scripts/worktree-clean.sh — prune stale Claude Code subagent worktrees.
#
# Claude Code spawns subagents with `isolation: "worktree"` into
# .claude/worktrees/agent-<hash>/. If an agent fails before its parent
# session can clean up, both the worktree directory AND the git
# `worktree-agent-<hash>` branch leak. This script:
#   1. force-removes any .claude/worktrees/agent-* whose lock pid is dead
#   2. runs `git worktree prune` to drop stale .git/worktrees/ entries
#   3. deletes orphaned `worktree-agent-*` branches with no live worktree
#
# Usage:  bash scripts/worktree-clean.sh [--dry-run]
#
# Safe to run anytime — refuses to touch worktrees whose lock pid is
# still alive (i.e. an agent is actively working there).

set -u

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=1
    echo "[dry-run] would-remove items will be printed; no changes made."
fi

run() {
    if [ "$DRY_RUN" = "1" ]; then
        echo "[dry-run] $*"
    else
        eval "$@"
    fi
}

# 1. Force-remove .claude/worktrees/agent-* with dead pid locks
if [ -d ".claude/worktrees" ]; then
    for wt in .claude/worktrees/agent-*; do
        [ -d "$wt" ] || continue
        wt_name=$(basename "$wt")
        lock_file=".git/worktrees/$wt_name/locked"
        if [ -f "$lock_file" ]; then
            # lock content: "claude agent agent-<hash> (pid <N>)"
            pid=$(grep -oE 'pid [0-9]+' "$lock_file" 2>/dev/null | awk '{print $2}')
            if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
                echo "⏳ $wt_name — live pid $pid, skipping"
                continue
            fi
            echo "🧹 $wt_name — dead pid ${pid:-?}, removing"
        else
            echo "🧹 $wt_name — no lock, removing"
        fi
        run "git worktree remove -f -f '$wt' 2>/dev/null || rm -rf '$wt'"
    done
fi

# 2. Prune git's view of stale worktrees
echo "🌲 git worktree prune"
run "git worktree prune -v"

# 3. Drop orphaned worktree-agent-* branches with no live worktree
for br in $(git branch --format='%(refname:short)' | grep '^worktree-agent-' || true); do
    if ! git worktree list --porcelain | grep -q "branch refs/heads/$br"; then
        echo "🌿 deleting orphan branch $br"
        run "git branch -D '$br'"
    fi
done

echo "✅ done"
