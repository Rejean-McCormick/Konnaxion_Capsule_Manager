"""
Canonical Konnaxion Capsule Manager UI page registry.

This module owns the framework-neutral page registry only. Page identity and
page metadata types live in kx_manager.ui.page_types. Navigation helpers live in
kx_manager.ui.page_navigation.
"""

from __future__ import annotations

from kx_manager.ui.page_types import PageDefinition, PageGroup, PageId


PAGE_REGISTRY: tuple[PageDefinition, ...] = (
    PageDefinition(
        page_id=PageId.DASHBOARD,
        title="Dashboard",
        route="/",
        group=PageGroup.OVERVIEW,
        description="Instance status, security state, backups, and quick actions.",
        icon="layout-dashboard",
        order=10,
    ),
    PageDefinition(
        page_id=PageId.CAPSULES,
        title="Capsules",
        route="/capsules",
        group=PageGroup.OPERATIONS,
        description="Verify, import, and inspect Konnaxion Capsules.",
        icon="package",
        order=20,
    ),
    PageDefinition(
        page_id=PageId.CAPSULE_IMPORT,
        title="Import Capsule",
        route="/capsules/import",
        group=PageGroup.OPERATIONS,
        nav_label="Import Capsule",
        description="Import a signed .kxcap file.",
        icon="upload",
        order=21,
        visible_in_nav=False,
    ),
    PageDefinition(
        page_id=PageId.INSTANCES,
        title="Instances",
        route="/instances",
        group=PageGroup.OPERATIONS,
        description="Create, start, stop, update, and inspect Konnaxion Instances.",
        icon="server",
        order=30,
    ),
    PageDefinition(
        page_id=PageId.INSTANCE_DETAIL,
        title="Instance Detail",
        route="/instances/detail",
        group=PageGroup.OPERATIONS,
        description="Detailed status for one Konnaxion Instance.",
        icon="server-cog",
        order=31,
        visible_in_nav=False,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.INSTANCE_CREATE,
        title="Create Instance",
        route="/instances/create",
        group=PageGroup.OPERATIONS,
        description="Create a new Konnaxion Instance from an imported Capsule.",
        icon="plus",
        order=32,
        visible_in_nav=False,
    ),
    PageDefinition(
        page_id=PageId.SECURITY,
        title="Security Gate",
        route="/security",
        group=PageGroup.SAFETY,
        description="Run and inspect Security Gate checks.",
        icon="shield-check",
        order=40,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.NETWORK,
        title="Network",
        route="/network",
        group=PageGroup.SAFETY,
        description="Choose canonical network profiles and exposure modes.",
        icon="network",
        order=50,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.BACKUPS,
        title="Backups",
        route="/backups",
        group=PageGroup.OPERATIONS,
        description="Create, verify, and inspect application backups.",
        icon="database-backup",
        order=60,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.RESTORE,
        title="Restore",
        route="/restore",
        group=PageGroup.OPERATIONS,
        description="Restore a backup into the same or a new Konnaxion Instance.",
        icon="rotate-ccw",
        order=70,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.LOGS,
        title="Logs",
        route="/logs",
        group=PageGroup.SYSTEM,
        description="View service and Agent logs.",
        icon="scroll-text",
        order=80,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.HEALTH,
        title="Health",
        route="/health",
        group=PageGroup.SYSTEM,
        description="View service healthchecks and runtime readiness.",
        icon="activity",
        order=90,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.SETTINGS,
        title="Settings",
        route="/settings",
        group=PageGroup.SYSTEM,
        description="Manager settings and runtime variables.",
        icon="settings",
        order=100,
    ),
    PageDefinition(
        page_id=PageId.ABOUT,
        title="About",
        route="/about",
        group=PageGroup.SYSTEM,
        description="Product and build information.",
        icon="info",
        order=110,
    ),
)


__all__ = [
    "PAGE_REGISTRY",
]