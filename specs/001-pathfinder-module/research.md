# Research: Pathfinder Module

**Date**: 2026-03-11
**Feature**: 001-pathfinder-module

## R1: Python 3.8 Compatibility for Dataclasses and Type Hints

**Decision**: Use `dataclasses.dataclass` with `Optional[str]` and `List[str]` from `typing` module instead of Python 3.10+ syntax.

**Rationale**: Project requires Python >= 3.8. `dataclasses` is available since 3.7. Union types (`str | None`) require 3.10+, so we use `Optional[str]`. `list[str]` as annotation requires 3.9+, so we use `List[str]` from typing or `from __future__ import annotations`.

**Alternatives considered**:
- `from __future__ import annotations` — allows `str | None` syntax in annotations at 3.8, but doesn't help runtime checks. Viable but could confuse contributors who expect runtime behavior.
- Plain dicts instead of dataclasses — less structured, no field validation. Rejected.

**Resolution**: Use `from __future__ import annotations` at module top + `dataclasses.dataclass`. This gives clean syntax while maintaining 3.8 compat.

## R2: Singleton Pattern for get_pathfinder()

**Decision**: Module-level singleton using a private global and factory function.

**Rationale**: All 7 consuming modules need the same resolved paths. Creating separate instances would waste cache and could yield inconsistent results if cwd changes between instantiations.

**Alternatives considered**:
- Class-level `__new__` singleton — more complex, harder to test (can't easily reset between tests).
- Module-level instance created at import time — prevents lazy initialization, breaks testing with monkeypatched `Path.home()`.
- Dependency injection — too heavy for this use case. Would require threading pathfinder through every function signature.

**Resolution**: Lazy-initialized module singleton with `_instance: Optional[Pathfinder] = None` and `get_pathfinder() -> Pathfinder`. Include `_reset_pathfinder()` for test isolation.

## R3: Executable Discovery Strategy Order

**Decision**: Ordered search matching current discovery.py behavior, parameterized per platform profile.

**Rationale**: discovery.py already implements 7 strategies that work. Pathfinder consolidates them into a single ordered list. Each platform profile declares which search paths are relevant (e.g., Goose doesn't need npm/nvm).

**Alternatives considered**:
- Platform-specific strategy classes — over-engineered for what's essentially an ordered list of paths to check.
- Parallel search — unnecessary complexity for a fast operation.

**Resolution**: Sequential search through: PATH → env override → npm global → npm prefix → nvm → virtualenv → conda → system paths → custom. Each PathProfile has `search_paths` for custom locations and `executable_names` for what to look for. Skip strategies that don't apply to the platform.

## R4: Project-Level Directory Search Depth

**Decision**: Default 5 levels up from cwd, configurable via constructor parameter.

**Rationale**: Typical project nesting is 2-3 levels. 5 is generous. Going higher risks hitting filesystem root on shallow trees (which is fine — search just stops).

**Alternatives considered**:
- Unlimited upward search — could be slow on deeply nested filesystems.
- Fixed at 3 levels — too restrictive for monorepos.

**Resolution**: `Pathfinder(project_search_depth=5)` default. Stop at filesystem root regardless.

## R5: Cache Invalidation Strategy

**Decision**: Manual invalidation via `clear_cache()`. No TTL for path resolution. Optional TTL consideration for executable lookups deferred.

**Rationale**: Path profiles are static. The filesystem layout for a platform doesn't change during a CLI invocation. Executable discovery is expensive (subprocess calls for npm prefix) but also rarely changes mid-session. Manual `clear_cache()` is sufficient for the library's use case (short-lived CLI commands).

**Alternatives considered**:
- TTL-based cache with 5-minute expiry — adds complexity (threading, time tracking) for a CLI tool that runs for seconds.
- No caching — acceptable for path resolution but wasteful for repeated executable lookups.

**Resolution**: Dict-based cache keyed by (platform_slug, method_name). `clear_cache()` empties all caches. No TTL — keep it simple.

## R6: Third-Party Profile Registration (R9 Plugin Architecture)

**Decision**: Support `entry_points` group `agent_transfer.path_profiles` for third-party registration, plus runtime `register_profile()` method.

**Rationale**: Constitution R9 requires plugin architecture. Entry points allow pip-installable platform extensions. Runtime registration allows test profiles and dynamic use.

**Alternatives considered**:
- Config file (YAML/JSON) for profiles — adds file I/O dependency, harder to version with code.
- Decorator-based registration — requires importing the third-party module, which defeats lazy discovery.

**Resolution**: `PathProfileRegistry` loads built-in profiles at init, then scans `entry_points(group='agent_transfer.path_profiles')` for third-party profiles. Also exposes `registry.register(profile)` for runtime additions.

## R7: translate_path() Approach

**Decision**: String-based prefix matching and replacement. Match the longest platform directory prefix, swap with target platform's equivalent directory.

**Rationale**: Path translation is fundamentally string manipulation — identify which platform directory a path belongs to, extract the relative portion, and prepend the target platform's equivalent. No need for complex AST or path parsing.

**Alternatives considered**:
- Regex-based matching — more fragile, harder to maintain.
- Path object decomposition — over-engineered for prefix replacement.

**Resolution**: For each registered platform, build a map of `(expanded_dir, dir_type)` pairs. Given an input path, find the longest matching prefix, determine its type (config/agents/skills/hooks), and construct the target path using the target platform's equivalent directory. Return original path + warning if no match found.

## R8: Handling Platforms Without Certain Directory Types

**Decision**: Return `None` for missing directory types. Document in API contract.

**Rationale**: Goose has no agents dir (uses recipes). OpenCode has no hooks. Returning `None` is Pythonic and lets callers handle gracefully with `if dir is not None`.

**Alternatives considered**:
- Raise exception — too aggressive for a query operation.
- Return empty Path — ambiguous, could be confused with a real but empty directory.

**Resolution**: Methods return `Optional[Path]`. `None` means "this platform doesn't have this directory type." Callers check before use.
