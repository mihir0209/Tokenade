# Datestamp Naming Convention - Benefits and Rationale

**Date:** 2026-06-01
**Status:** Active
**Type:** Process Documentation

## Convention

All plans, reviews, and documentation files use the format:

```
YYYY-MM-DD-title-slug.md
```

Examples:
- `2026-06-01-architecture-design.md`
- `2026-06-01-implementation-roadmap.md`
- `2026-06-01-ja3-tls-fingerprint-matching.md`

## Benefits

### 1. Chronological Ordering
Files automatically sort by date in file explorers and `ls` output:
```
2026-06-01-architecture-design.md
2026-06-01-implementation-roadmap.md
2026-06-01-next-phase-testing-coverage.md
2026-06-15-ja3-tls-fingerprint-matching.md  # Later date
```

### 2. Context at a Glance
Immediately know when a document was created and whether it's recent or outdated:
- `2026-06-01-*` - Current sprint (relevant)
- `2025-12-01-*` - Six months old (may be outdated)
- `2024-01-01-*` - Legacy (likely irrelevant)

### 3. Prevents Naming Collisions
No more `plan-v2-final-REALLY-FINAL.md`:
```
# Bad
01-architecture.md
02-architecture.md
architecture-final.md

# Good
2026-06-01-architecture-design.md
2026-06-15-architecture-revised.md
```

### 4. Easy Cleanup
Quickly identify and archive old documents:
```bash
# Find plans older than 90 days
find .agent/plans/ -name "*.md" -mtime +90

# Archive old plans
mv .agent/plans/2025-* .agent/archive/
```

### 5. Git History Clarity
Git log shows meaningful dates in filenames:
```
2026-06-01  Added: architecture-design.md
2026-06-01  Added: implementation-roadmap.md
2026-06-01  Added: next-phase-testing-coverage.md
```

### 6. Cross-Reference Friendly
When plans reference each other, dates make dependencies clear:
```markdown
See [2026-06-01-architecture-design.md](2026-06-01-architecture-design.md)
for the foundation this plan builds upon.
```

## Directory Structure

```
.agent/
├── plans/
│   ├── 2026-06-01-architecture-design.md
│   ├── 2026-06-01-implementation-roadmap.md
│   ├── 2026-06-01-next-phase-testing-coverage.md
│   ├── 2026-06-01-additional-site-handlers.md
│   ├── 2026-06-01-ja3-tls-fingerprint-matching.md
│   ├── 2026-06-01-web-dashboard-rest-api.md
│   └── 2026-06-01-distributed-session-management.md
├── reviews/
│   └── 2026-06-01-code-review.md
└── archive/          # Old plans moved here
    └── 2025-*
```

## Migration Notes

All existing documentation has been renamed to follow this convention.
Old numeric prefixes (`01-`, `02-`) have been replaced with dates.

| Old Name | New Name |
|----------|----------|
| `01-architecture.md` | `2026-06-01-architecture-design.md` |
| `02-implementation.md` | `2026-06-01-implementation-roadmap.md` |
| `01-code-review.md` | `2026-06-01-code-review.md` |

## Future Documents

When creating new plans or reviews:
1. Use today's date as prefix
2. Use kebab-case for the title slug
3. Keep it descriptive but concise
4. Add metadata header (Date, Status, Priority)
