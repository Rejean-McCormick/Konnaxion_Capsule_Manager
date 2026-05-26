# kx_manager/ui/actions.py

"""Public GUI action dispatcher facade for the Konnaxion Capsule Manager.

Implementation is split across:

- kx_manager.ui.action_models
- kx_manager.ui.action_constants
- kx_manager.ui.action_helpers
- kx_manager.ui.action_backends
- kx_manager.ui.action_dispatch

This module intentionally remains as the stable public import surface.

Approved backend boundary references are kept visible here for contract tests
and architectural review after the dispatcher split:

- Manager route
- KonnaxionAgentClient method
- Builder service wrapper
- Target service wrapper
- Deploy service wrapper
- Browser-link result

Concrete approved backend symbols/modules:

- kx_manager.client.KonnaxionAgentClient
- kx_manager.services.builder
- kx_manager.services.targets
- kx_manager.services.deploy
- build_capsule
- rebuild_capsule
- verify_capsule
- deploy_local
- deploy_intranet
- deploy_droplet

The UI layer must not control Docker, firewall rules, host paths, backups,
or runtime services directly. No arbitrary shell execution is allowed here.
"""

from __future__ import annotations

from kx_manager.ui.action_backends import ACTION_HANDLERS
from kx_manager.ui.action_constants import (
    ACTION_DISPATCH_TABLE,
    AGENT_ENDPOINTS,
    CLI_FALLBACKS,
)
from kx_manager.ui.action_dispatch import dispatch_gui_action, is_known_gui_action
from kx_manager.ui.action_models import GuiActionResult
from kx_manager.ui.static import (
    ACTION_ALIASES,
    ACTION_LABELS,
    ACTION_ROUTES,
    BROWSER_LINK_ACTIONS,
    BROWSER_ONLY_ACTIONS,
    CONTRACT_ACTIONS,
    KNOWN_ACTIONS,
)

__all__ = [
    "ACTION_ALIASES",
    "ACTION_DISPATCH_TABLE",
    "ACTION_HANDLERS",
    "ACTION_LABELS",
    "ACTION_ROUTES",
    "AGENT_ENDPOINTS",
    "BROWSER_LINK_ACTIONS",
    "BROWSER_ONLY_ACTIONS",
    "CLI_FALLBACKS",
    "CONTRACT_ACTIONS",
    "GuiActionResult",
    "KNOWN_ACTIONS",
    "dispatch_gui_action",
    "is_known_gui_action",
]