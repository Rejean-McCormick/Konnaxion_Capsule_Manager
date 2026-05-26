# kx_manager/ui/page_parts/about.py

"""About page body for the Konnaxion Capsule Manager GUI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kx_manager.ui.form_constants import DEFAULT_CAPSULE_ID, DEFAULT_INSTANCE_ID
from kx_manager.ui.page_parts.common import (
    APP_TITLE,
    UI_BASE_PATH,
    action_bar,
    button_form,
    safety_note,
)
from kx_manager.ui.render import render_card, render_definition_list, render_grid, render_link


def render(context: Mapping[str, Any]) -> str:
    """Render the About page body."""

    body = render_definition_list(
        {
            "Product": "Konnaxion",
            "Manager": APP_TITLE,
            "Capsule extension": ".kxcap",
            "Default instance": DEFAULT_INSTANCE_ID,
            "Default target": "intranet",
            "UI base path": UI_BASE_PATH,
        }
    )

    docs = action_bar(
        [
            render_link("FastAPI Docs", "/docs", button=True),
            render_link("OpenAPI", "/openapi.json", button=True),
            button_form("open_manager_docs", "Manager Docs"),
            button_form("open_agent_docs", "Agent Docs"),
        ]
    )

    return render_grid(
        [
            render_card("About", body, footer=docs),
            safety_note(),
        ]
    )


__all__ = ["render"]
