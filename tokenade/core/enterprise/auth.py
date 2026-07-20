"""
Role-Based Access Control (RBAC) for Tokenade.

Provides fine-grained access control with:
- Role definitions
- Permission management
- User-role assignments
- Access verification
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class Permission:
    """A permission grant."""
    
    resource: str  # e.g., "session", "vault", "sync"
    action: str    # e.g., "read", "write", "delete", "admin"
    
    def __str__(self):
        return f"{self.resource}:{self.action}"
    
    def __eq__(self, other):
        if isinstance(other, Permission):
            return self.resource == other.resource and self.action == other.action
        return False
    
    def __hash__(self):
        return hash((self.resource, self.action))
    
    @classmethod
    def from_string(cls, s: str) -> 'Permission':
        """Parse 'resource:action' string."""
        parts = s.split(":", 1)
        if len(parts) == 2:
            return cls(resource=parts[0], action=parts[1])
        return cls(resource=parts[0], action="*")
    
    def matches(self, required: 'Permission') -> bool:
        """Check if this permission matches a required permission."""
        if self.resource == "*" or self.resource == required.resource:
            if self.action == "*" or self.action == required.action:
                return True
        return False


@dataclass
class Role:
    """A role with associated permissions."""
    
    name: str
    description: str = ""
    permissions: List[Permission] = field(default_factory=list)
    parent_roles: List[str] = field(default_factory=list)
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if role has a specific permission."""
        for p in self.permissions:
            if p.matches(permission):
                return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permissions": [str(p) for p in self.permissions],
            "parent_roles": self.parent_roles,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Role':
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            permissions=[Permission.from_string(p) for p in data.get("permissions", [])],
            parent_roles=data.get("parent_roles", []),
        )


@dataclass
class User:
    """A user with assigned roles."""
    
    user_id: str
    username: str
    email: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    active: bool = True
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "roles": self.roles,
            "active": self.active,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        return cls(
            user_id=data.get("user_id", ""),
            username=data.get("username", ""),
            email=data.get("email"),
            roles=data.get("roles", []),
            active=data.get("active", True),
            created_at=data.get("created_at", time.time()),
        )


class RBACManager:
    """
    Role-Based Access Control manager.
    
    Features:
    - Role and permission management
    - User-role assignments
    - Hierarchical roles
    - Access verification
    - Persistent storage
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self._config_path = Path(config_path or "~/.tokenade/rbac.json").expanduser()
        self._roles: Dict[str, Role] = {}
        self._users: Dict[str, User] = {}
        self._init_default_roles()
        self._load()
    
    def _init_default_roles(self):
        """Initialize default roles."""
        self._roles["admin"] = Role(
            name="admin",
            description="Full system access",
            permissions=[
                Permission("*", "*"),
            ],
        )
        
        self._roles["operator"] = Role(
            name="operator",
            description="Can manage sessions and sync",
            permissions=[
                Permission("session", "read"),
                Permission("session", "write"),
                Permission("session", "delete"),
                Permission("sync", "read"),
                Permission("sync", "write"),
                Permission("vault", "read"),
            ],
        )
        
        self._roles["viewer"] = Role(
            name="viewer",
            description="Read-only access",
            permissions=[
                Permission("session", "read"),
                Permission("sync", "read"),
            ],
        )
        
        self._roles["auditor"] = Role(
            name="auditor",
            description="Audit log access",
            permissions=[
                Permission("audit", "read"),
                Permission("audit", "write"),
            ],
        )
    
    def create_role(
        self,
        name: str,
        description: str = "",
        permissions: Optional[List[str]] = None,
        parent_roles: Optional[List[str]] = None,
    ) -> Role:
        """Create a new role."""
        role = Role(
            name=name,
            description=description,
            permissions=[Permission.from_string(p) for p in (permissions or [])],
            parent_roles=parent_roles or [],
        )
        
        self._roles[name] = role
        self._save()
        return role
    
    def delete_role(self, name: str) -> bool:
        """Delete a role."""
        if name in ("admin", "operator", "viewer"):
            return False
        
        if name in self._roles:
            del self._roles[name]
            
            for user in self._users.values():
                if name in user.roles:
                    user.roles.remove(name)
            
            self._save()
            return True
        return False
    
    def get_role(self, name: str) -> Optional[Role]:
        """Get a role by name."""
        return self._roles.get(name)
    
    def list_roles(self) -> List[Role]:
        """List all roles."""
        return list(self._roles.values())
    
    def create_user(
        self,
        user_id: str,
        username: str,
        email: Optional[str] = None,
        roles: Optional[List[str]] = None,
    ) -> User:
        """Create a new user."""
        user = User(
            user_id=user_id,
            username=username,
            email=email,
            roles=roles or ["viewer"],
        )
        
        self._users[user_id] = user
        self._save()
        return user
    
    def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        if user_id in self._users:
            del self._users[user_id]
            self._save()
            return True
        return False
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        return self._users.get(user_id)
    
    def list_users(self) -> List[User]:
        """List all users."""
        return list(self._users.values())
    
    def assign_role(self, user_id: str, role_name: str) -> bool:
        """Assign a role to a user."""
        user = self._users.get(user_id)
        role = self._roles.get(role_name)
        
        if not user or not role:
            return False
        
        if role_name not in user.roles:
            user.roles.append(role_name)
            self._save()
        
        return True
    
    def revoke_role(self, user_id: str, role_name: str) -> bool:
        """Revoke a role from a user."""
        user = self._users.get(user_id)
        
        if not user:
            return False
        
        if role_name in user.roles:
            user.roles.remove(role_name)
            self._save()
            return True
        
        return False
    
    def check_permission(self, user_id: str, permission: Permission) -> bool:
        """
        Check if a user has a specific permission.
        
        Args:
            user_id: User ID to check
            permission: Permission to check
            
        Returns:
            True if user has the permission
        """
        user = self._users.get(user_id)
        if not user or not user.active:
            return False
        
        for role_name in user.roles:
            role = self._roles.get(role_name)
            if role:
                if role.has_permission(permission):
                    return True
                
                for parent_name in role.parent_roles:
                    parent = self._roles.get(parent_name)
                    if parent and parent.has_permission(permission):
                        return True
        
        return False
    
    def get_user_permissions(self, user_id: str) -> Set[Permission]:
        """Get all permissions for a user."""
        user = self._users.get(user_id)
        if not user:
            return set()
        
        permissions = set()
        
        for role_name in user.roles:
            role = self._roles.get(role_name)
            if role:
                permissions.update(role.permissions)
                
                for parent_name in role.parent_roles:
                    parent = self._roles.get(parent_name)
                    if parent:
                        permissions.update(parent.permissions)
        
        return permissions
    
    def _load(self):
        """Load configuration from disk."""
        if self._config_path.exists():
            try:
                with open(self._config_path) as f:
                    data = json.load(f)
                
                for role_data in data.get("roles", []):
                    role = Role.from_dict(role_data)
                    self._roles[role.name] = role
                
                for user_data in data.get("users", []):
                    user = User.from_dict(user_data)
                    self._users[user.user_id] = user
                    
            except Exception as e:
                logger.warning(f"Failed to load RBAC config: {e}")
    
    def _save(self):
        """Save configuration to disk."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "roles": [role.to_dict() for role in self._roles.values()],
                "users": [user.to_dict() for user in self._users.values()],
            }
            
            with open(self._config_path, "w") as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to save RBAC config: {e}")
