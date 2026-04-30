"""Konnaxion Agent package.

The Agent is the controlled privileged service used by the Konnaxion Capsule
Manager to manage capsules, instances, Docker Compose runtime operations,
network profiles, backups, restores, and Security Gate checks.

Package-level metadata is imported from the shared canonical registry so this
module does not define independent product names, versions, paths, states, or
service identifiers.
"""

from kx_shared.konnaxion_constants import AGENT_NAME, APP_VERSION

__all__ = [
    "__app_name__",
    "__version__",
]

__app_name__ = AGENT_NAME
__version__ = APP_VERSION
