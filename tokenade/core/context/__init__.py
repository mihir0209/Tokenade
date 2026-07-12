"""Shared context module for the Tokenade ecosystem.

Core owns it. Plugins read/write through provided API.
4 namespaces: Sessions, Plugins, Config, Runtime.

Public API:
- SharedContext: Main context class (singleton)
- SessionsNamespace: Session data and health
- PluginsNamespace: Plugin registration and config
- ConfigNamespace: User preferences and settings
- RuntimeNamespace: Transient runtime state
- TaskTracker: Plugin task lifecycle tracking
- TaskState: Task state enum

Example:
    from tokenade.core.context import SharedContext

    ctx = SharedContext()
    ctx.sessions.set("s1", {"cookies": {...}})
    ctx.config.set_registry_url("https://registry.dev")
    proxy = ctx.runtime.get_active_proxy()
"""

from tokenade.core.context.config import ConfigNamespace
from tokenade.core.context.context import SharedContext
from tokenade.core.context.plugins import PluginsNamespace
from tokenade.core.context.runtime import RuntimeNamespace
from tokenade.core.context.sessions import SessionsNamespace
from tokenade.core.context.tasks import TaskState, TaskTracker

__all__ = [
    "SharedContext",
    "SessionsNamespace",
    "PluginsNamespace",
    "ConfigNamespace",
    "RuntimeNamespace",
    "TaskTracker",
    "TaskState",
]
