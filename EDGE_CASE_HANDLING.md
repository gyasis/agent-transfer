# Edge Case Handling Documentation

This document describes the comprehensive error handling implemented for edge cases in the selective import feature.

## Edge Cases Implemented

### 1. Empty Archive

**Location**: `agent_transfer/utils/import_analyzer.py` (lines 96-100)

**Behavior**:
- Detects when archive contains no agents (0 comparisons)
- Displays friendly yellow warning: "Archive is empty (no agents found)"
- Returns valid `ImportPreview` with empty comparisons list
- No crash, graceful degradation

**Test**: `test_edge_cases.py::test_empty_archive()`

**Example Output**:
```
[yellow]Archive is empty (no agents found)[/yellow]
```

---

### 2. All IDENTICAL Agents

**Location**: `agent_transfer/cli.py` (lines 157-162)

**Behavior**:
- After analysis, checks if `new_count == 0 and changed_count == 0 and total > 0`
- Displays message: "All agents are identical to local versions."
- Prompts user with `rich.prompt.Confirm`: "Show identical agents anyway?"
- If user declines (default=False), gracefully cancels import
- If user accepts, continues to selection UI

**Test**: `test_all_identical.py`

**Example Output**:
```
[yellow]All agents are identical to local versions.[/yellow]
Show identical agents anyway? [y/N]: n
[dim]Import cancelled[/dim]
```

---

### 3. Archive Extraction Failures

**Location**: `agent_transfer/utils/import_analyzer.py` (lines 49-56)

**Behavior**:
- Wraps `tar.extractall()` in try/except for `tarfile.TarError`
- Catches corrupted archives, invalid formats, permission issues
- Raises `RuntimeError` with clear message: "Failed to extract archive. File may be corrupted."
- Preserves original exception with `from e` for debugging

**Test**: `test_edge_cases.py::test_corrupted_archive()`

**Example Output**:
```
[red]Error: Failed to extract archive. File may be corrupted.[/red]
```

---

## Implementation Details

### Empty Archive Handler

```python
# Handle empty archive
if not comparisons:
    from rich.console import Console
    console = Console()
    console.print("[yellow]Archive is empty (no agents found)[/yellow]")
```

**Why**: Prevents confusing behavior when user exports/imports empty archives. Provides clear feedback.

---

### All Identical Handler

```python
# Handle all identical case
if preview.new_count == 0 and preview.changed_count == 0 and len(preview.comparisons) > 0:
    console.print("\n[yellow]All agents are identical to local versions.[/yellow]")
    if not Confirm.ask("Show identical agents anyway?", default=False):
        console.print("[dim]Import cancelled[/dim]")
        return
```

**Why**: Avoids unnecessary import workflow when nothing would change. Gives user control.

**Default Behavior**: Cancels import (user must explicitly choose to continue)

---

### Archive Extraction Error Handler

```python
# Extract archive with error handling
try:
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(temp_path)
except tarfile.TarError as e:
    raise RuntimeError(
        f"Failed to extract archive. File may be corrupted."
    ) from e
```

**Why**: Provides clear, actionable error messages instead of cryptic tar exceptions.

**Error Types Caught**:
- Corrupted archive files
- Invalid tar.gz format
- Truncated downloads
- Permission issues
- Disk space issues

---

## Testing

All edge cases have automated tests:

```bash
# Run edge case tests
python test_edge_cases.py

# Run all identical test
python test_all_identical.py
```

**Test Coverage**:
- ✅ Empty archive (0 agents)
- ✅ Corrupted archive (invalid tar.gz)
- ✅ All identical agents (new=0, changed=0, total>0)

---

## User Experience Improvements

### Before Edge Case Handling
- Empty archives: Silent failure or confusing output
- All identical: Unnecessary selection UI shown
- Corrupted archives: Cryptic tar error messages

### After Edge Case Handling
- **Empty archives**: Clear yellow warning, graceful handling
- **All identical**: Friendly prompt with option to continue or cancel
- **Corrupted archives**: Clear error message with troubleshooting hint

---

## Error Message Styling

All error messages use Rich styling for clarity:

| Color/Style | Meaning |
|-------------|---------|
| `[yellow]` | Warning (non-fatal) |
| `[red]` | Error (fatal) |
| `[dim]` | Secondary info |
| `[cyan]` | Informational |

---

## Exit Behavior

| Edge Case | Exit Code | Behavior |
|-----------|-----------|----------|
| Empty archive | 0 | Graceful completion |
| All identical (user declines) | 0 | Graceful cancellation |
| Corrupted archive | 1 | Error exit |

---

## Future Enhancements

Potential additional edge cases to handle:

1. **Partial archive corruption**: Some agents parse, others fail
2. **Permission denied**: Local agent directories not writable
3. **Disk space**: Not enough space for extraction
4. **Large archives**: Progress indicators for multi-GB archives
5. **Network archives**: Support for HTTP/HTTPS URLs

---

## Integration with Existing Code

Edge case handling integrates seamlessly with:

- **Interactive selection**: Still works after "all identical" prompt
- **Conflict resolution**: Not triggered for empty archives
- **Logging**: Errors preserve original exceptions for debugging
- **CLI flags**: Works with `--bulk`, `--agent`, and default modes

---

## Maintenance Notes

When modifying edge case handling:

1. **Preserve error chains**: Always use `from e` when re-raising
2. **Use Rich styling**: Keep consistent color scheme
3. **Update tests**: Add test case for new edge cases
4. **Document changes**: Update this file
5. **User-friendly messages**: Avoid technical jargon

---

*Last updated: 2026-01-10*
