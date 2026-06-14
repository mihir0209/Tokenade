# Manual Test Report — Enterprise Features

**Date:** 2026-06-14
**Version:** v3.4.0

## Test 1: Audit Logger

### Command
```bash
python -c "
from tokenade.core.security.audit import AuditLogger
import tempfile, os

with tempfile.TemporaryDirectory() as tmpdir:
    log_path = os.path.join(tmpdir, 'audit.log')
    logger = AuditLogger(log_path=log_path)
    
    logger.log_event('session_export', session_id='s1', site_name='google')
    logger.log_event('session_share', session_id='s1', method='email')
    logger.log_event('session_export', session_id='s2', site_name='github')
    logger.log_event('session_refresh', session_id='s1')
    
    events = logger.query_events()
    print(f'Total events: {len(events)}')
    
    exports = logger.query_events(event_type='session_export')
    print(f'Export events: {len(exports)}')
    
    summary = logger.get_summary()
    print(f'Summary: {summary}')
"
```

### Result
- **Status:** PASS
- **Output:**
  ```
  Total events: 4
  Export events: 2
  Summary: {'session_export': 2, 'session_share': 1, 'session_refresh': 1}
  ```

## Test 2: Role-Based Access Control

### Command
```bash
python -c "
from tokenade.core.security.audit import RoleManager
import tempfile, os

with tempfile.TemporaryDirectory() as tmpdir:
    rbac = RoleManager(storage_path=os.path.join(tmpdir, 'rbac.json'))
    
    rbac.assign_role('admin@test.com', 'admin')
    rbac.assign_role('user@test.com', 'viewer')
    rbac.assign_role('editor@test.com', 'editor')
    
    users = rbac.list_users()
    print(f'Users: {len(users)}')
    for u in users:
        print(f'  {u[\"user_id\"]}: {u[\"role\"]}')
"
```

### Result
- **Status:** PASS
- **Output:** 3 users with correct roles assigned

## Test 3: LDAP Authenticator Initialization

### Command
```bash
python -c "
from tokenade.core.security.audit import LDAPAuthenticator, LDAPConfig

config = LDAPConfig(
    server='ldap.example.com',
    port=636,
    use_ssl=True,
    bind_dn='cn=admin,dc=example,dc=com',
    bind_password='test',
    user_search_base='ou=users,dc=example,dc=com',
    user_search_filter='(uid={username})',
)
auth = LDAPAuthenticator(config)
print(f'LDAP available: {auth._ldap_available}')
# Should gracefully handle missing ldap3
result = auth.authenticate('testuser', 'password')
print(f'Auth result: {result}')
"
```

### Result
- **Status:** PASS
- **Output:** Graceful fallback when ldap3 not installed (returns False)

## Test 4: Docker Manager Initialization

### Command
```bash
python -c "
from tokenade.core.integration.docker_manager import DockerSessionManager

manager = DockerSessionManager()
print(f'Docker available: {manager.is_available()}')
status = manager.get_status()
print(f'Status: {status}')
"
```

### Result
- **Status:** PASS
- **Output:** Docker manager initializes correctly (availability depends on Docker installation)

## Test 5: Kubernetes Manager YAML Generation

### Command
```bash
python -c "
from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

config = KubernetesConfig(namespace='production', replicas=2)
k8s = KubernetesManager(config)

deployment = k8s.generate_deployment_yaml()
print(f'Deployment YAML length: {len(deployment)} chars')
print(f'Contains apiVersion: {\"apiVersion\" in deployment}')
print(f'Contains kind Deployment: {\"kind: Deployment\" in deployment}')

service = k8s.generate_service_yaml()
print(f'Service YAML length: {len(service)} chars')
"
```

### Result
- **Status:** PASS
- **Output:** Valid Kubernetes YAML generated for Deployment and Service

## Test 6: Plugin Registry

### Command
```bash
python -c "
from tokenade.core.integration.plugin_registry import PluginRegistry
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    registry = PluginRegistry(registry_url='https://raw.githubusercontent.com/test/test/main', plugins_dir=tmpdir)
    installed = registry.list_installed()
    print(f'Installed plugins: {len(installed)}')
"
```

### Result
- **Status:** PASS
- **Output:** Empty plugin list (expected - no plugins installed)
