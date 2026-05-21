#!/usr/bin/env bash
# install.sh — wire up agent-transfer for Claude Code discoverability (A + B + C)
#
# A. Copies skill.md → ~/.claude/skills/agent-transfer.md  (session-start awareness)
# B. Copies rule.md  → ~/.claude/rules/tools/agent-transfer.md  (in-task reinforcement)
# C. Symlinks ~/bin/{ab,agent-transfer} → venv shim  (shell discoverability)
#
# Idempotent — safe to re-run. Refuses to overwrite existing skill/rule unless --force.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2; exit 2
      ;;
  esac
done

SKILLS_DIR="$HOME/.claude/skills"
RULES_DIR="$HOME/.claude/rules/tools"
BIN_DIR="$HOME/bin"
VENV_SHIM="$REPO_ROOT/.venv/bin/agent-transfer"

# Sanity checks
if [[ ! -f "$VENV_SHIM" ]]; then
  echo "ERROR: venv shim not found at $VENV_SHIM" >&2
  echo "       Install agent-transfer first (see ../README.md → Installation)." >&2
  exit 1
fi

mkdir -p "$SKILLS_DIR" "$RULES_DIR" "$BIN_DIR"

# ---- A: skill ----
SKILL_DEST="$SKILLS_DIR/agent-transfer.md"
if [[ -e "$SKILL_DEST" && $FORCE -eq 0 ]]; then
  echo "[A] skill already exists at $SKILL_DEST (use --force to overwrite)"
else
  cp "$SCRIPT_DIR/skill.md" "$SKILL_DEST"
  echo "[A] installed skill → $SKILL_DEST"
fi

# ---- B: rule ----
RULE_DEST="$RULES_DIR/agent-transfer.md"
if [[ -e "$RULE_DEST" && $FORCE -eq 0 ]]; then
  echo "[B] rule already exists at $RULE_DEST (use --force to overwrite)"
else
  cp "$SCRIPT_DIR/rule.md" "$RULE_DEST"
  echo "[B] installed rule  → $RULE_DEST"
fi

# ---- C: symlinks ----
for name in agent-transfer ab; do
  target="$BIN_DIR/$name"
  if [[ -L "$target" && "$(readlink "$target")" == "$VENV_SHIM" ]]; then
    echo "[C] symlink already correct: $target → $VENV_SHIM"
  else
    ln -sf "$VENV_SHIM" "$target"
    echo "[C] linked → $target"
  fi
done

echo
echo "Done. Verify:"
echo "  which ab && ab --version"
echo
echo "Next Claude Code session will surface the skill at session start."
