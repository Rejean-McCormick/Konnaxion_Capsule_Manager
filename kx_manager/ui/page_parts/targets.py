# kx_manager/ui/page_parts/targets.py

"""Targets page body for the Konnaxion Capsule Manager GUI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kx_manager.ui.page_parts.common import (
    action_form,
    confirmed_field,
    droplet_payload,
    field,
    instance_id_field,
    intranet_payload,
    local_payload,
    temporary_public_payload,
)
from kx_manager.ui.render import render_card, render_grid


REMOTE_AGENT_URL_HELP = (
    "Optional. Leave blank for the normal private Droplet Agent. "
    "Blank means the Manager reaches http://127.0.0.1:8765/v1 inside "
    "the Droplet over SSH. Use this only for an explicit tunnel such as "
    "http://127.0.0.1:18765/v1."
)


def render(context: Mapping[str, Any]) -> str:
    """Render the Targets page body."""

    local = local_payload(context)
    intranet = intranet_payload(context)
    temporary_public = temporary_public_payload(context)
    droplet = droplet_payload(context)

    local_form = action_form(
        "set_target_local",
        [
            instance_id_field(local["instance_id"]),
            field(
                "runtime_root",
                "Runtime Root",
                local["runtime_root"],
                required=True,
            ),
            field(
                "capsule_dir",
                "Capsule Directory",
                local["capsule_dir"],
                required=True,
            ),
        ],
        hidden={
            "target_mode": "local",
            "network_profile": "local_only",
            "exposure_mode": "private",
            "public_mode_enabled": "false",
            "public_mode_expires_at": "",
            "confirmed": "",
        },
    )

    intranet_form = action_form(
        "set_target_intranet",
        [
            instance_id_field(intranet["instance_id"]),
            field(
                "runtime_root",
                "Runtime Root",
                intranet["runtime_root"],
                required=True,
            ),
            field(
                "capsule_dir",
                "Capsule Directory",
                intranet["capsule_dir"],
                required=True,
            ),
            field(
                "host",
                "Private Host",
                intranet["host"],
                required=False,
            ),
            field(
                "exposure_mode",
                "Exposure Mode",
                intranet["exposure_mode"],
                field_type="select",
                required=True,
                options=[
                    ("private", "Private"),
                    ("lan", "LAN"),
                ],
            ),
        ],
        hidden={
            "target_mode": "intranet",
            "network_profile": "intranet_private",
            "public_mode_enabled": "false",
            "public_mode_expires_at": "",
            "confirmed": "",
        },
    )

    temporary_public_form = action_form(
        "set_target_temporary_public",
        [
            instance_id_field(temporary_public["instance_id"]),
            field(
                "runtime_root",
                "Runtime Root",
                temporary_public["runtime_root"],
                required=True,
            ),
            field(
                "capsule_dir",
                "Capsule Directory",
                temporary_public["capsule_dir"],
                required=True,
            ),
            field(
                "public_host",
                "Public Host",
                temporary_public["public_host"],
                required=True,
            ),
            field(
                "public_mode_expires_at",
                "Public Mode Expires At",
                temporary_public["public_mode_expires_at"],
                required=True,
                help_text="ISO-8601 datetime.",
            ),
            confirmed_field("I confirm temporary public exposure"),
        ],
        hidden={
            "target_mode": "temporary_public",
            "network_profile": "public_temporary",
            "exposure_mode": "temporary_tunnel",
            "public_mode_enabled": "true",
        },
    )

    droplet_form = action_form(
        "set_target_droplet",
        [
            instance_id_field(droplet["instance_id"]),
            field(
                "droplet_name",
                "Droplet Name",
                droplet["droplet_name"],
                required=True,
            ),
            field(
                "droplet_host",
                "Droplet Host / IP",
                droplet["droplet_host"],
                required=True,
            ),
            field(
                "droplet_user",
                "SSH User",
                droplet["droplet_user"],
                required=True,
            ),
            field(
                "ssh_key_path",
                "SSH Key Path",
                droplet["ssh_key_path"],
                required=True,
            ),
            field(
                "ssh_port",
                "SSH Port",
                droplet["ssh_port"],
                field_type="number",
                required=True,
            ),
            field(
                "remote_kx_root",
                "Remote KX Root",
                droplet["remote_kx_root"],
                required=True,
            ),
            field(
                "remote_capsule_dir",
                "Remote Capsule Directory",
                droplet["remote_capsule_dir"],
                required=True,
            ),
            field(
                "domain",
                "Domain",
                droplet["domain"],
                required=True,
                help_text=(
                    "Required public DNS name, sslip.io host, "
                    "or accepted public host alias."
                ),
            ),
            field(
                "remote_agent_url",
                "Remote Agent URL",
                droplet["remote_agent_url"],
                required=False,
                help_text=REMOTE_AGENT_URL_HELP,
            ),
            confirmed_field("I confirm public VPS target configuration"),
        ],
        hidden={
            "target_mode": "droplet",
            "network_profile": "public_vps",
            "exposure_mode": "public",
            "public_mode_enabled": "true",

            # Public runtime host values.
            #
            # These must be the browser/public domain, not the Droplet SSH IP.
            # Agent-side runtime generation uses these values for KX_HOST,
            # NEXT_PUBLIC_API_BASE, NEXT_PUBLIC_BACKEND_BASE, Django allowed
            # hosts/origins, and Traefik Host(...) rules.
            "host": droplet["domain"],
            "public_host": droplet["domain"],
            "domain": droplet["domain"],
            "droplet_domain": droplet["domain"],

            # SSH / remote target values.
            #
            # These remain the machine address used to reach the VPS over SSH.
            "droplet_host": droplet["droplet_host"],
            "target_host": droplet["droplet_host"],

            # Remote runtime paths.
            "runtime_root": droplet["remote_kx_root"],
            "capsule_dir": droplet["remote_capsule_dir"],
            "remote_kx_root": droplet["remote_kx_root"],
            "remote_capsule_dir": droplet["remote_capsule_dir"],
        },
    )

    return render_grid(
        [
            render_card("Local Target", local_form),
            render_card("Intranet Target", intranet_form),
            render_card(
                "Temporary Public Target",
                temporary_public_form,
                classes="kx-result warn",
            ),
            render_card(
                "Droplet Target",
                droplet_form,
                classes="kx-result warn",
            ),
        ]
    )


__all__ = ["render"]