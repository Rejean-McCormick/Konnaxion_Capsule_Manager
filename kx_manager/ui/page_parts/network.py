# kx_manager/ui/page_parts/network.py

"""Network page body for the Konnaxion Capsule Manager GUI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kx_manager.ui.page_parts.common import (
    action_form,
    confirmed_field,
    context_value,
    default_payload,
    exposure_mode_field,
    field,
    instance_id_field,
    network_profile_field,
)
from kx_manager.ui.render import render_card, render_grid


def render(context: Mapping[str, Any]) -> str:
    """Render the Network page body."""

    payload = default_payload(context)

    set_form = action_form(
        "set_network_profile",
        [
            instance_id_field(payload["instance_id"]),
            network_profile_field(str(payload["network_profile"])),
            exposure_mode_field(str(payload["exposure_mode"])),
            field("host", "Host", payload["host"], required=False),
            field("domain", "Domain", context_value(context, "domain", default=""), required=False),
            field(
                "public_mode_expires_at",
                "Public Mode Expires At",
                context_value(context, "public_mode_expires_at", default=""),
                required=False,
                help_text="Required for temporary public mode.",
            ),
            field("confirmed", "I confirm public exposure if selected", False, field_type="checkbox"),
        ],
    )

    disable_form = action_form(
        "disable_public_mode",
        [
            instance_id_field(payload["instance_id"]),
            confirmed_field("I confirm disabling public mode"),
        ],
        submit_label="Disable Public Mode",
    )

    return render_grid(
        [
            render_card("Set Network Profile", set_form),
            render_card("Disable Public Mode", disable_form, classes="kx-result warn"),
        ]
    )


__all__ = ["render"]
