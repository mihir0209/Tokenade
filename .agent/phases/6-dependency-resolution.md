# Phase 6: Dependency Resolution

**Objective:** Implement plugin dependency resolution. Topological sort, latest version wins, depth limit 5, circular dependency detection.

**Status:** NOT STARTED
**Dependencies:** Phase 4, Phase 5
**Blocks:** Phase 7

---

## Scope

### IN
- Implement dependency resolution in plugin loader
- Implement topological sort for load order
- Implement circular dependency detection
- Implement version conflict resolution
- Implement depth limit enforcement
- CLI commands for dependency management
- Unit tests for dependency resolution

### OUT
- No plugin installation yet (existing registry handles that)
- No TUI integration yet (Phase 10)

---

## Strict Rules

1. **Topological sort** — Plugins load in dependency order
2. **Latest version wins** — On version conflict, latest version is used
3. **Depth limit 5** — Maximum dependency chain depth is 5
4. **Circular detection** — Circular dependencies are detected and rejected
5. **Dependency installation** — Missing dependencies are installed automatically
6. **Test everything** — Every edge case has tests
7. **No commits until tests pass**

---

## Detailed Tasks

### T6.1: Implement Dependency Graph
**File:** `tokenade/core/integration/dependency_graph.py`

```python
class DependencyGraph:
    def add_plugin(name, dependencies)
    def remove_plugin(name)
    def get_dependencies(name) -> List[str]
    def get_dependents(name) -> List[str]
    def topological_sort() -> List[str]
    def has_cycle() -> bool
    def get_depth(name) -> int
    def validate() -> List[str]
```

**Rules:**
- Graph is built from plugin manifests
- Topological sort returns load order
- Cycle detection uses DFS
- Depth is calculated from root plugins
- Validation returns list of errors

### T6.2: Implement Dependency Resolver
**File:** `tokenade/core/integration/dependency_resolver.py`

```python
class DependencyResolver:
    def __init__(graph, registry_manager)
    def resolve(plugin_name) -> List[str]
    def install_with_dependencies(plugin_name)
    def check_missing() -> List[str]
    def check_circular() -> List[str]
    def check_depth() -> List[str]
    def _install_dependency(dep_name)
```

**Rules:**
- Resolver uses topological sort for load order
- Missing dependencies are installed automatically
- Circular dependencies are detected and rejected
- Depth limit is enforced (max 5)
- Version conflicts resolved by latest version

### T6.3: Implement Version Conflict Resolution
**File:** `tokenade/core/integration/dependency_resolver.py`

**Changes:**
- When two plugins need different versions of same dependency
- Compare versions using semver
- Latest version wins
- Log warning when version conflict occurs

**Rules:**
- Version comparison uses semver (major.minor.patch)
- Major version mismatch is a conflict
- Minor version mismatch uses latest
- Patch version mismatch uses latest

### T6.4: Implement Depth Limit Enforcement
**File:** `tokenade/core/integration/dependency_resolver.py`

**Changes:**
- Calculate dependency depth for each plugin
- Reject plugins with depth > 5
- Log warning when depth limit approached

**Rules:**
- Depth is calculated from root (no dependencies = depth 0)
- Maximum depth is 5
- Depth limit is enforced during load
- Depth limit is enforced during install

### T6.5: Implement CLI Commands
**File:** `tokenade/cli/__init__.py`

**New commands:**
```bash
tokenade plugin deps <name>              # Show dependency tree
tokenade plugin check-deps               # Check for missing dependencies
tokenade plugin install <name>           # Install with dependencies
```

**Rules:**
- `deps` shows dependency tree (indented)
- `check-deps` lists missing dependencies
- `install` installs dependencies automatically

### T6.6: Write Unit Tests
**File:** `tests/test_dependency_resolution.py`

**Test cases:**
- DependencyGraph: add/remove plugins
- DependencyGraph: topological sort
- DependencyGraph: cycle detection
- DependencyGraph: depth calculation
- DependencyResolver: resolve dependencies
- DependencyResolver: install with dependencies
- DependencyResolver: missing dependencies
- DependencyResolver: circular dependencies
- DependencyResolver: depth limit
- Version conflict: latest version wins
- CLI: deps command
- CLI: check-deps command
- CLI: install with dependencies

---

## Files to Create

| File | Purpose |
|------|---------|
| `tokenade/core/integration/dependency_graph.py` | DependencyGraph |
| `tokenade/core/integration/dependency_resolver.py` | DependencyResolver |
| `tests/test_dependency_resolution.py` | Unit tests |

## Files to Modify

| File | Changes |
|------|---------|
| `tokenade/cli/__init__.py` | Add dependency commands |

---

## Verification

- [ ] DependencyGraph builds correctly
- [ ] Topological sort returns correct order
- [ ] Circular dependencies detected
- [ ] Depth limit enforced
- [ ] Missing dependencies installed automatically
- [ ] Version conflicts resolved (latest wins)
- [ ] CLI commands work
- [ ] All tests pass
- [ ] No commits until all tests pass
