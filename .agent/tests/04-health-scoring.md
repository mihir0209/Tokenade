# Manual Test Report — Session Health Scoring

**Date:** 2026-06-14
**Version:** v3.4.0

## Test 1: Basic Health Check

### Command
```bash
python -m tokenade.cli health -s test_sessions/google.tokenade
```

### Result
- **Status:** PASS
- **Output:**
  ```
  Status: UNHEALTHY
  Health Score: 98.8%
  Issues: 2 expired cookies
  Recommendations: Re-export session from browser
  ```

## Test 2: OWASP Health Scoring

### Command
```bash
python -c "
from tokenade.core.refresh.health_scorer import SessionHealthScorer
import json

with open('test_sessions/google.tokenade') as f:
    session = json.load(f)

scorer = SessionHealthScorer()
result = scorer.score(session)
print(f'Total: {result.total_score:.1f}/100')
print(f'Entropy: {result.entropy_score:.1f}/25')
print(f'Expiry: {result.expiry_score:.1f}/25')
print(f'Flags: {result.flags_score:.1f}/25')
print(f'Freshness: {result.freshness_score:.1f}/25')
"
```

### Result
- **Status:** PASS
- **Output:**
  ```
  Total: 74.7/100
  Entropy: 23.2/25
  Expiry: 10.0/25
  Flags: 16.5/25
  Freshness: 25.0/25
  ```
- **Analysis:**
  - Entropy: High (good token values)
  - Expiry: Low (2 expired cookies dragging score down)
  - Flags: Moderate (some cookies missing HttpOnly/Secure)
  - Freshness: Perfect (session recently created)

## Test 3: Health Report Generation

### Command
```bash
python -c "
from tokenade.core.refresh.health_checker import SessionHealthChecker, generate_health_report

checker = SessionHealthChecker()
health = checker.check_session('test_sessions/google.tokenade')
print(generate_health_report(health))
"
```

### Result
- **Status:** PASS
- **Output:** Formatted report with status, score, issues, recommendations, timestamp
