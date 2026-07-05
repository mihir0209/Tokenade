"""
CLI Command Handlers — organized by category.

Each handler file contains cmd_ functions that are imported
by tokenade.cli.__init__ for dispatch.
"""

# Re-export handler functions for backward compatibility
from tokenade.cli.handlers.infrastructure import cmd_fleet  # noqa: F401
from tokenade.cli.handlers.ci import (  # noqa: F401
    cmd_cicd, cmd_ci, cmd_autopsy, cmd_cloak, cmd_tui,
)
from tokenade.cli.handlers.misc import cmd_monitor, cmd_analytics, cmd_daemon  # noqa: F401
