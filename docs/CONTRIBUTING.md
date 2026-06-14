# Contributing to Tokenade

## Development Setup

```bash
git clone https://github.com/mihir0209/Tokenade.git
cd Tokenade
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium --with-deps
```

## Running Tests

```bash
# All tests
python -m pytest tokenade/tests/ -v

# Quick (skip slow tests)
python -m pytest tokenade/tests/ -m "not slow" -v

# With coverage
python -m pytest tokenade/tests/ --cov=tokenade --cov-report=html

# Benchmarks only
python -m pytest tokenade/tests/test_benchmarks.py -v
```

## Code Style

- **Formatter**: Black (line length 120)
- **Linter**: Flake8
- **Type checker**: Mypy
- **Python**: 3.10+

```bash
make format    # Auto-format
make lint      # Check style
make typecheck # Type check
```

## Project Structure

```
tokenade/
├── core/
│   ├── antidetection/     # CDP cleanup, behavioral injection
│   ├── api/               # REST API server
│   ├── batch/             # Batch export/load operations
│   ├── browser/           # Browser manager
│   ├── crypto/            # Encryption, cookie crypto
│   ├── errors.py          # Custom exception hierarchy
│   ├── fingerprint/       # Fingerprint management
│   ├── importer/          # Session extraction, loading, sharing
│   ├── injector/          # Profile injection
│   ├── integration/       # Docker, K8s, plugins, webhooks
│   ├── monitoring/        # Session health monitoring
│   ├── proxy/             # CDP proxy, forward proxy, multi-site
│   ├── refresh/           # Health scoring, auto-refresh
│   ├── runtime/           # TLS matcher, runtime engine
│   ├── security/          # Audit, RBAC, LDAP, credentials
│   └── utils/             # Performance utilities
├── cli/                   # CLI modules (9 files)
├── handlers/              # Site-specific handlers
├── sdk/                   # Python SDK
└── tests/                 # 1042+ tests
```

## Adding a Plugin

### Plugin Types

1. **Site Handler** — Custom cookie extraction for a specific site
2. **Export Format** — Custom output format
3. **Validator** — Custom health check rules

### Plugin Structure

```
~/.tokenade/plugins/my-plugin/
├── plugin.json          # Manifest
└── handler.py           # Entry point
```

### plugin.json

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My custom plugin",
  "author": "Your Name",
  "type": "handler",
  "site_name": "example.com",
  "entry_point": "handler.py",
  "entry_class": "ExampleHandler"
}
```

### handler.py

```python
class ExampleHandler:
    def check_auth(self, cookies):
        """Check if user is authenticated."""
        return any(c["name"] == "session_id" for c in cookies)

    def extract_tokens(self, cookies):
        """Extract auth tokens from cookies."""
        return [c for c in cookies if c["name"] == "session_id"]
```

## Testing Guidelines

- Write tests for all new features
- Use `pytest` fixtures for shared setup
- Use `hypothesis` for property-based testing
- Benchmark critical operations in `test_benchmarks.py`
- Keep tests fast — mock external dependencies

## Commit Messages

- Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- Reference issues: `fix #123`
- Keep messages concise (<72 chars)

## Pull Requests

1. Create a feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass
4. Update documentation if needed
5. Submit PR with clear description
