# kx_manager/ui/page_parts/settings.py

"""Settings page body for the Konnaxion Capsule Manager GUI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kx_manager.ui.form_constants import (
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_OUTPUT_DIR,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_CHANNEL,
    DEFAULT_INSTANCE_ID,
    DEFAULT_RUNTIME_ROOT,
    DEFAULT_SOURCE_DIR,
)
from kx_manager.ui.page_parts.common import (
    action_form,
    capsule_output_dir_field,
    context_value,
    source_dir_field,
)
from kx_manager.ui.render import render_card, render_definition_list, render_grid


def render(context: Mapping[str, Any]) -> str:
    """Render the Settings page body."""

    source_form = action_form(
        "select_source_folder",
        [source_dir_field(context_value(context, "source_dir", default=DEFAULT_SOURCE_DIR))],
    )

    output_form = action_form(
        "select_capsule_output_folder",
        [
            capsule_output_dir_field(
                context_value(
                    context,
                    "capsule_output_dir",
                    "output_dir",
                    default=DEFAULT_CAPSULE_OUTPUT_DIR,
                )
            )
        ],
    )

    defaults = render_definition_list(
        {
            "Default instance": DEFAULT_INSTANCE_ID,
            "Default capsule": DEFAULT_CAPSULE_ID,
            "Default capsule version": DEFAULT_CAPSULE_VERSION,
            "Default channel": DEFAULT_CHANNEL,
            "Default runtime root": DEFAULT_RUNTIME_ROOT,
            "Default source folder": DEFAULT_SOURCE_DIR,
            "Default capsule output folder": DEFAULT_CAPSULE_OUTPUT_DIR,
        }
    )

    return render_grid(
        [
            render_card("Source Folder", source_form),
            render_card("Capsule Output Folder", output_form),
            render_card("Current Defaults", defaults),
        ]
    )


__all__ = ["render"]
