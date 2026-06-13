# Contributing to Tokenade

Thank you for your interest in contributing to Tokenade! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Pull Requests](#pull-requests)
- [Code Style](#code-style)
- [Documentation](#documentation)

## Code of Conduct

Please be respectful and constructive in all interactions. We are committed to providing a welcoming and inclusive experience for everyone.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a branch for your feature or fix
4. Make your changes
5. Run tests to ensure nothing is broken
6. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.8+
- pip
- git

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/tokenade.git
cd tokenade

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

# Install in development mode
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium
```

### Project Structure

```
tokenade/
├── core/
│   ├── proxy/           # Proxy implementations
│   ├── runtime/         # TLS matching, engine
│   ├── importer/        # Session extraction, packaging
│   ├── injector/        # Profile injection
│   ├── crypto/          # Encryption, cookie decryption
│   ├── security/        # Credentials, SSRF protection
│   └── batch/           # Batch operations
├── handlers/            # Site-specific handlers
├── tests/               # Test suite
├── cli.py               # CLI entry point
└── utils/               # Utilities
```

## Making Changes

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation changes
- `test/description` - Test additions

### Commit Messages

Use clear, descriptive commit messages:

```
Add session auto-refresh feature

- Implement SessionRefresher class
- Monitor cookie expiry during proxy operation
- Auto-refresh from source browser if enabled
- Add /session/status and /session/refresh API endpoints
```

### Code Conventions

1. **Follow PEP 8** - Use black for formatting
2. **Type hints** - Add type hints to all functions
3. **Docstrings** - Add docstrings to all public functions
4. **Error handling** - Use generic error messages to users, log details
5. **Security** - Never log secrets, always sanitize user input

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tokenade/tests/test_session_refresher.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=tokenade
```

### Writing Tests

1. **Unit tests** - Test individual functions/methods
2. **Integration tests** - Test component interactions
3. **Use fixtures** - Create reusable test fixtures
4. **Mock external dependencies** - Use unittest.mock
5. **Test edge cases** - Test error conditions and边界值

### Test File Naming

- `test_<module>.py` - Tests for `<module>.py`
- Place in `tokenade/tests/` directory
- Use descriptive test names

Example:

```python
class TestSessionRefresher:
    @pytest.fixture
    def session(self):
        return {
            "site_name": "test",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
            ],
        }

    def test_check_expiry_no_expiry(self, session):
        refresher = SessionRefresher(session)
        status = refresher.check_expiry()
        assert status.expired_count == 0
```

## Pull Requests

### Before Submitting

1. Ensure all tests pass
2. Update documentation if needed
3. Add changelog entry if significant change
4. Verify no secrets are committed

### PR Template

```markdown
## Description

Brief description of changes

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist

- [ ] Code follows project style
- [ ] Tests pass locally
- [ ] Documentation updated
- [ ] No sensitive data committed
```

## Code Style

### Python

- Use black for formatting: `black tokenade/`
- Use flake8 for linting: `flake8 tokenade/`
- Use mypy for type checking: `mypy tokenade/`

### Imports

```python
# Standard library
import asyncio
import json
from pathlib import Path

# Third-party
import aiohttp
import pytest

# Local
from tokenade.core.importer.session_packager import SessionPackager
```

### Type Hints

```python
from typing import Optional, Dict, List

def process_session(
    session: Dict,
    config: Optional[Config] = None,
) -> List[Result]:
    """Process session with optional config."""
    pass
```

### Error Handling

```python
# Bad - exposes internal details
except Exception as e:
    print(f"Error: {e}")

# Good - generic message to user, details logged
except Exception as e:
    logger.error(f"Failed to process session: {e}")
    print("Failed to process session. Check logs for details.")
```

## Documentation

### Types of Documentation

1. **API Reference** - `docs/API.md`
2. **Architecture** - `docs/ARCHITECTURE.md`
3. **Security** - `docs/SECURITY.md`
4. **CLI Help** - Built-in `--help` flags

### Writing Documentation

- Use clear, concise language
- Include code examples
- Keep examples up-to-date
- Document both parameters and return values

## Questions?

If you have questions about contributing, feel free to:

1. Open an issue for discussion
2. Check existing documentation
3. Review similar implementations in the codebase

Thank you for contributing to Tokenade!
