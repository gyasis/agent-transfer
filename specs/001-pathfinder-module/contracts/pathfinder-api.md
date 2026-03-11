# API Contract: Pathfinder Module

**Module**: `agent_transfer.utils.pathfinder`
**Date**: 2026-03-11

## Public API

### Module-Level Functions

#### `get_pathfinder() -> Pathfinder`
Returns the module singleton. Creates on first call. Thread-safe via simple check-and-set.

#### `_reset_pathfinder() -> None`
Resets the singleton. **Test use only.** Allows test isolation.

---

### Class: Pathfinder

#### Constructor

```
Pathfinder(project_search_depth: int = 5)
```

Creates a Pathfinder with built-in profiles loaded and entry_points scanned.

---

#### Directory Resolution

```
config_dir(slug: str) -> Path
```
Returns the absolute path to the platform's config directory. Checks env override first, falls back to `Path.home() / profile.config_dir`.

**Raises**: `KeyError` if slug not registered.

---

```
agents_dir(slug: str) -> Optional[Path]
```
Returns absolute path to agents directory, or `None` if platform has no agents dir.

---

```
skills_dir(slug: str) -> Optional[Path]
```
Returns absolute path to skills directory, or `None` if platform has no skills dir.

---

```
hooks_dir(slug: str) -> Optional[Path]
```
Returns absolute path to hooks directory, or `None` if platform has no hooks dir.

---

```
config_files(slug: str) -> List[Path]
```
Returns list of absolute paths to known config files for the platform.

---

#### Project-Level Resolution

```
project_agents_dir(slug: str, start_dir: Optional[Path] = None) -> Optional[Path]
```
Searches upward from `start_dir` (default: `Path.cwd()`) for a project-level agents directory. Returns `None` if not found or platform doesn't support project-level dirs.

---

```
project_skills_dir(slug: str, start_dir: Optional[Path] = None) -> Optional[Path]
```
Same as above for skills.

---

```
all_agents_dirs(slug: str) -> List[Tuple[Path, str]]
```
Returns all agents directories (user + project) as `(path, scope)` tuples where scope is `"user"` or `"project"`.

---

```
all_skills_dirs(slug: str) -> List[Tuple[Path, str]]
```
Same as above for skills.

---

#### Executable Discovery

```
find_executable(slug: str) -> Optional[Path]
```
Searches for the platform's executable using the consolidated strategy order. Returns `None` if not found. Results are cached.

---

#### Path Remapping

```
remap_path(path: Path, source_home: str, target_home: str) -> Path
```
Replaces `source_home` prefix with `target_home`. Returns path unchanged if prefix doesn't match or path is relative.

---

#### Cross-Platform Translation

```
translate_path(path: str, from_platform: str, to_platform: str) -> Tuple[str, Optional[str]]
```
Translates a path from one platform's directory structure to another's. Returns `(translated_path, warning)` where warning is `None` on success or a message if path couldn't be fully translated.

---

#### Path Utilities

```
validate_path(path: Path) -> bool
```
Returns `True` if path exists and is readable.

---

```
ensure_dir(path: Path) -> Path
```
Creates directory (and parents) if it doesn't exist. Returns the path.

---

#### Registry & Cache

```
supported_platforms() -> List[str]
```
Returns all registered platform slugs.

---

```
register_profile(profile: PathProfile) -> None
```
Registers a new platform profile or replaces an existing one.

---

```
clear_cache() -> None
```
Clears all cached resolution results.

---

## Error Contract

| Condition | Behavior |
|-----------|----------|
| Unknown platform slug | `KeyError` with message listing valid slugs |
| Platform has no directory of requested type | Returns `None` |
| Executable not found | Returns `None` |
| Path remapping with non-matching prefix | Returns original path unchanged |
| Path translation with unknown source path | Returns `(original_path, "warning message")` |
| Environment override points to non-existent dir | Returns the override path anyway (caller validates) |

## Backward Compatibility

All existing module behavior is preserved. Pathfinder is additive — consuming modules produce the same outputs, just sourced through pathfinder instead of direct `Path.home()` construction.
