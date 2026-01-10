# Selective Import Implementation

## Summary

Added `import_agents_selective()` function to `/home/gyasis/Documents/code/agent-transfer/agent_transfer/utils/transfer.py` (lines 315-446).

## Function Signature

```python
def import_agents_selective(
    archive_path: str,
    selected_comparisons: List[AgentComparison],
    conflict_mode: ConflictMode,
    total_in_archive: int
) -> Dict[str, int]:
```

## Parameters

- **archive_path**: Path to the tar.gz backup archive
- **selected_comparisons**: List of `AgentComparison` objects representing agents selected for import
- **conflict_mode**: One of `ConflictMode.OVERWRITE`, `KEEP`, `DUPLICATE`, or `DIFF` (interactive)
- **total_in_archive**: Total count of agents in archive (used for statistics)

## Return Value

Dictionary with import statistics:
```python
{
    'new_imported': int,        # Number of NEW agents imported
    'changed_imported': int,    # Number of CHANGED agents imported
    'identical_skipped': int,   # Number of IDENTICAL agents skipped
    'not_selected': int         # Number of agents not selected for import
}
```

## Implementation Details

### Archive Extraction
- Uses `tempfile.TemporaryDirectory()` context manager for automatic cleanup
- Extracts archive to temporary location
- Preserves directory structure (`user-agents/` and `project-agents/`)

### Agent Processing Logic

For each `AgentComparison` in `selected_comparisons`:

1. **Determine paths**:
   - User agents: `~/.claude/agents/`
   - Project agents: `<cwd>/.claude/agents/`

2. **Status-based handling**:

   - **NEW**: Direct copy via `shutil.copy2()`
     ```python
     shutil.copy2(source_path, target_path)
     new_imported += 1
     ```

   - **CHANGED**: Conflict resolution via `resolve_conflict()`
     ```python
     result = resolve_conflict(
         existing_path=target_path,
         incoming_path=source_path,
         target_dir=target_dir,
         mode=conflict_mode
     )
     if result:
         changed_imported += 1
     ```

   - **IDENTICAL**: Skip with log message
     ```python
     console.print(f"[dim]Skipping {filename} (identical)[/dim]")
     identical_skipped += 1
     ```

### Summary Display

Uses Rich Panel to show formatted summary:
```
╭──────────── Import Complete ────────────╮
│ Imported: 5 agents                      │
│   NEW: 3                                │
│   CHANGED: 2                            │
│                                         │
│ Skipped: 8 agents                       │
│   IDENTICAL: 3                          │
│   NOT SELECTED: 5                       │
╰─────────────────────────────────────────╯
```

## Key Features

1. **Nested directory support**: Uses `rglob("*.md")` to handle nested archive structures
2. **Type-aware**: Distinguishes user vs. project agents for correct target directory
3. **Metadata preservation**: Displays backup metadata from archive
4. **Progress logging**: Rich-formatted console output for each agent
5. **Error handling**: Warns if agent file not found in archive
6. **Directory creation**: Ensures target directories exist via `mkdir(parents=True, exist_ok=True)`
7. **Automatic cleanup**: Temporary directory automatically removed via context manager

## Integration Points

### Required Imports
Already present in `transfer.py`:
- `shutil` - File operations
- `tempfile` - Temporary directory
- `Path` from pathlib
- `List`, `Dict` from typing
- `AgentComparison` from models
- `ConflictMode`, `resolve_conflict` from conflict_resolver
- `Console`, `Panel` from rich

### Usage Example
```python
from agent_transfer.utils.transfer import import_agents_selective
from agent_transfer.utils.conflict_resolver import ConflictMode

# Assume preview was generated earlier
selected = [comp for comp in preview.comparisons if comp.agent.name in selected_names]

stats = import_agents_selective(
    archive_path="agents-backup.tar.gz",
    selected_comparisons=selected,
    conflict_mode=ConflictMode.DIFF,
    total_in_archive=len(preview.comparisons)
)

print(f"Imported {stats['new_imported']} new agents")
print(f"Updated {stats['changed_imported']} existing agents")
```

## Testing

Validated:
- Python syntax compilation
- Function imports successfully
- Correct type hints
- Parameter names match specification
- Return type matches specification

## Files Modified

1. `/home/gyasis/Documents/code/agent-transfer/agent_transfer/utils/transfer.py`
   - Added `Dict` to typing imports (line 9)
   - Added `import_agents_selective()` function (lines 315-446)

## Notes

- Function follows existing patterns from `import_agents()` for consistency
- Reuses conflict resolution logic from `conflict_resolver.py`
- Preserves file metadata with `shutil.copy2()`
- Console output uses Rich library for formatted display
- No changes to existing functions or CLI commands
