# kx_manager/ui/server.py

"""Development ASGI server entrypoint for the Konnaxion Manager GUI."""

from __future__ import annotations

from fastapi import FastAPI

from kx_manager.ui.app import register


app = FastAPI(title="Konnaxion Capsule Manager")
register(app)


__all__ = [
    "app",
]