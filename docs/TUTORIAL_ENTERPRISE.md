# Enterprise Deployment Guide

## Overview

Tokenade provides enterprise features for teams: audit logging, role-based access control (RBAC), and LDAP/SSO integration.

## Audit Logging

Track all session operations for compliance (SOC 2, GDPR, HIPAA).

### Setup

```python
from tokenade.core.security.audit import AuditLogger

# Default: logs to ~/.tokenade/audit.jsonl
logger = AuditLogger()

# Custom log location
logger = AuditLogger(log_dir="/var/log/tokenade")
```

### Logging Events

```python
# Log session export
logger.log_event(
    "session_export",
    user="alice@company.com",
    session_id="s1",
    site_name="github.com",
    browser="firefox"
)

# Log session share
logger.log_event(
    "session_share",
    user="alice@company.com",
    session_id="s1",
    method="email",
    recipient="bob@company.com"
)

# Log session access
logger.log_event(
    "session_access",
    user="bob@company.com",
    session_id="s1",
    action="proxy_start"
)
```

### Querying Logs

```python
# Get all events
events = logger.get_events()

# Filter by user
events = logger.get_events(user="alice@company.com")

# Filter by event type
events = logger.get_events(event_type="session_export")

# Get summary
summary = logger.get_summary()
print(f"Total events: {summary['total_events']}")
print(f"Unique users: {summary['unique_users']}")
```

### Log Rotation

```python
# Rotate logs (keeps last 30 days)
logger.rotate(keep_days=30)
```

## Role-Based Access Control (RBAC)

Control who can export, share, and access sessions.

### Roles

| Role | Permissions |
|------|-------------|
| `admin` | Full access: export, share, revoke, manage users |
| `editor` | Export and share sessions |
| `viewer` | View session metadata only |

### Setup

```python
from tokenade.core.security.audit import RoleManager

rbac = RoleManager()
```

### Assigning Roles

```python
# Assign roles
rbac.assign_role("alice@company.com", "admin")
rbac.assign_role("bob@company.com", "editor")
rbac.assign_role("charlie@company.com", "viewer")
```

### Checking Permissions

```python
# Check if user can export
rbac.check_permission("bob@company.com", "export_session")  # True
rbac.check_permission("charlie@company.com", "export_session")  # False

# Check if user can share
rbac.check_permission("bob@company.com", "share_session")  # True
rbac.check_permission("charlie@company.com", "share_session")  # False

# Check if user can revoke
rbac.check_permission("bob@company.com", "revoke_share")  # False
rbac.check_permission("alice@company.com", "revoke_share")  # True
```

### Listing Roles

```python
# Get all roles
roles = rbac.list_roles()
# {"alice@company.com": "admin", "bob@company.com": "editor", ...}

# Get users with a specific role
admins = rbac.get_users_by_role("admin")
```

## LDAP/SSO Integration

Authenticate users against your LDAP directory.

### Setup

```python
from tokenade.core.security.audit import LDAPAuthenticator, LDAPConfig

config = LDAPConfig(
    server="ldap.company.com",
    port=636,
    use_ssl=True,
    bind_dn="cn=tokenade,ou=services,dc=company,dc=com",
    bind_password="service-password",
    user_search_base="ou=users,dc=company,dc=com",
    user_search_filter="(uid={username})",
    group_search_base="ou=groups,dc=company,dc=com",
    group_search_filter="(member={dn})",
)

auth = LDAPAuthenticator(config)
```

### Authentication

```python
# Authenticate user
result = auth.authenticate("alice", "password123")
print(result.success)  # True
print(result.user_dn)  # "uid=alice,ou=users,dc=company,dc=com"
print(result.groups)  # ["developers", "tokenade-users"]
```

### Group-Based Access

```python
# Check if user is in a specific group
if "tokenade-admins" in result.groups:
    rbac.assign_role(f"{username}@company.com", "admin")
elif "tokenade-users" in result.groups:
    rbac.assign_role(f"{username}@company.com", "editor")
```

### Graceful Fallback

If LDAP is unavailable, Tokenade falls back to local authentication:

```python
# LDAP connection fails -> falls back to file-based auth
result = auth.authenticate("alice", "password123")
# Falls back to local credential store
```

## Docker Deployment

```bash
# Build image
docker build -t tokenade .

# Run with LDAP config
docker run --rm -p 9222:9222 \
  -v ./sessions:/app/sessions:ro \
  -v ~/.tokenade:/root/.tokenade \
  --cap-add=SYS_ADMIN \
  tokenade proxy --host 0.0.0.0 -s /app/sessions/session.tokenade
```

## Kubernetes Deployment

```python
from tokenade.core.integration import KubernetesManager, KubernetesConfig

k8s = KubernetesManager(KubernetesConfig(namespace="production"))

# Generate sidecar YAML
print(k8s.generate_sidecar_yaml("my-app:latest", "tokenade-sessions"))

# Generate full deployment
print(k8s.generate_deployment_yaml(session_configmap="tokenade-sessions"))
```

## Security Best Practices

1. **Encrypt session files** — Always use `tokenade encrypt` for storage
2. **Use RBAC** — Restrict export/share permissions
3. **Enable audit logging** — Track all session operations
4. **Rotate sessions** — Use `tokenade refresh` to re-export periodically
5. **Limit network access** — Proxy binds to `127.0.0.1` by default
6. **Use HTTPS** — For API server in production
7. **Monitor health** — Use `tokenade health` to check session validity

## Compliance

### SOC 2

- Audit logging tracks all session operations
- RBAC controls access to session data
- LDAP integration centralizes authentication

### GDPR

- Session files can be encrypted at rest
- Audit logs can be purged on schedule
- User access can be revoked via RBAC

### HIPAA

- All session operations are logged
- Access is controlled via RBAC + LDAP
- Encryption protects PHI in session files
