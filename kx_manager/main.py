"""Konnaxion Capsule Manager entrypoint.

The Manager is the user-facing control layer. It presents capsule, instance,
security, network, backup, and log operations, but it must not directly control
Docker, firewall rules, system services, or host state. Privileged operations
belong to the Konnaxion Agent.

This module provides:

- a FastAPI application factory for local Manager API/UI hosting
- safe route auto-registration
- a small CLI entrypoint for local development/runtime launch

Canonical product metadata is imported from ``kx_shared.konnaxion_constants``.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
from dataclasses import dataclass
from typing import Iterable

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    MANAGER_NAME,
    PARAM_VERSION,
    PRODUCT_NAME,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_MANAGER_HOST = "127.0.0.1"
DEFAULT_MANAGER_PORT = 8714

ROUTE_MODULES = (
    "kx_manager.routes.capsules",
    "kx_manager.routes.instances",
    "kx_manager.routes.security",
    "kx_manager.routes.network",
    "kx_manager.routes.backups",
    "kx_manager.routes.logs",
)


class ManagerStartupError(RuntimeError):
    """Raised when the Manager cannot start safely."""


@dataclass(frozen=True)
class ManagerRuntimeConfig:
    """Runtime configuration for the local Manager process."""

    host: str = DEFAULT_MANAGER_HOST
    port: int = DEFAULT_MANAGER_PORT
    reload: bool = False
    log_level: str = "info"
    enable_docs: bool = True

    @classmethod
    def from_env(cls) -> "ManagerRuntimeConfig":
        """Load runtime settings from process environment.

        These variables configure only the local Manager process. They are not
        capsule/instance runtime variables and do not replace canonical KX_*
        values used by instances.
        """

        return cls(
            host=os.getenv("KONNAXION_MANAGER_HOST", DEFAULT_MANAGER_HOST),
            port=_parse_port(os.getenv("KONNAXION_MANAGER_PORT"), DEFAULT_MANAGER_PORT),
            reload=_parse_bool(os.getenv("KONNAXION_MANAGER_RELOAD"), default=False),
            log_level=os.getenv("KONNAXION_MANAGER_LOG_LEVEL", "info"),
            enable_docs=_parse_bool(os.getenv("KONNAXION_MANAGER_ENABLE_DOCS"), default=True),
        )


def create_app():
    """Create the Konnaxion Capsule Manager FastAPI application."""

    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ManagerStartupError(
            "FastAPI is required to run Konnaxion Capsule Manager. "
            "Install runtime dependencies with: pip install fastapi uvicorn"
        ) from exc

    app = FastAPI(
        title=MANAGER_NAME,
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        description=(
            "Local user-facing control layer for importing, starting, stopping, "
            "updating, securing, backing up, and monitoring Konnaxion Instances."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1",
            "http://localhost",
            "http://127.0.0.1:8714",
            "http://localhost:8714",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    register_builtin_routes(app)
    register_optional_ui(app)

    return app


def register_builtin_routes(app, route_modules: Iterable[str] = ROUTE_MODULES) -> None:
    """Register Manager API route modules if they are present.

    Route modules may expose either:

    - ``router``: a FastAPI APIRouter
    - ``register(app)``: a custom registration function

    Missing modules are tolerated so file-level implementation can progress
    incrementally without breaking the Manager entrypoint.
    """

    for module_name in route_modules:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                LOGGER.debug("Skipping missing Manager route module: %s", module_name)
                continue
            raise

        register = getattr(module, "register", None)
        router = getattr(module, "router", None)

        if callable(register):
            register(app)
            LOGGER.debug("Registered Manager route module via register(): %s", module_name)
            continue

        if router is not None:
            app.include_router(router)
            LOGGER.debug("Registered Manager APIRouter: %s", module_name)
            continue

        LOGGER.warning(
            "Manager route module %s has no router or register(app); skipped",
            module_name,
        )


def register_optional_ui(app) -> None:
    """Register the optional local UI module if available."""

    try:
        module = importlib.import_module("kx_manager.ui.app")
    except ModuleNotFoundError as exc:
        if exc.name == "kx_manager.ui.app":
            LOGGER.debug("Skipping missing Manager UI module")
            return
        raise

    register = getattr(module, "register", None)
    if callable(register):
        register(app)
        LOGGER.debug("Registered Manager UI module")
    else:
        LOGGER.warning("kx_manager.ui.app has no register(app); skipped")


def health_payload() -> dict[str, str]:
    """Return a minimal Manager health payload."""

    return {
        "product": PRODUCT_NAME,
        "component": MANAGER_NAME,
        "app_version": APP_VERSION,
        "param_version": PARAM_VERSION,
        "status": "ok",
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the Manager CLI parser."""

    env_config = ManagerRuntimeConfig.from_env()

    parser = argparse.ArgumentParser(
        prog="konnaxion-manager",
        description="Run the local Konnaxion Capsule Manager.",
    )
    parser.add_argument(
        "--host",
        default=env_config.host,
        help=f"Manager bind host. Default: {env_config.host}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=env_config.port,
        help=f"Manager bind port. Default: {env_config.port}",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=env_config.reload,
        help="Enable development reload.",
    )
    parser.add_argument(
        "--log-level",
        default=env_config.log_level,
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        help=f"Uvicorn log level. Default: {env_config.log_level}",
    )
    return parser


def run_server(config: ManagerRuntimeConfig) -> None:
    """Run the Manager ASGI server."""

    if config.host not in {"127.0.0.1", "localhost", "::1"}:
        LOGGER.warning(
            "Manager is binding to %s. The Manager UI/API should normally stay local; "
            "public exposure belongs to Konnaxion runtime through Traefik only.",
            config.host,
        )

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ManagerStartupError(
            "uvicorn is required to run Konnaxion Capsule Manager. "
            "Install runtime dependencies with: pip install uvicorn"
        ) from exc

    uvicorn.run(
        "kx_manager.main:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        reload=config.reload,
        log_level=config.log_level,
    )


def main(argv: list[str] | None = None) -> int:
    """Command-line entrypoint."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args(argv)

    config = ManagerRuntimeConfig(
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )

    try:
        run_server(config)
    except ManagerStartupError as exc:
        LOGGER.error("%s", exc)
        return 2

    return 0


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False

    raise ManagerStartupError(f"invalid boolean environment value: {value!r}")


def _parse_port(value: str | None, default: int) -> int:
    if not value:
        return default

    try:
        port = int(value)
    except ValueError as exc:
        raise ManagerStartupError(f"invalid Manager port: {value!r}") from exc

    if port <= 0 or port > 65535:
        raise ManagerStartupError(f"Manager port out of range: {port}")

    return port


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
