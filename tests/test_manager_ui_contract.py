"""
Contract tests for the Konnaxion Capsule Manager GUI.

These tests intentionally verify module boundaries and public contracts instead
of implementation details. The GUI must remain FastAPI-compatible, local-first,
canonical-value driven, and free from arbitrary shell execution.
"""

from __future__ import annotations

import builtins
import importlib
import inspect
import sys
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping

import pytest


REQUIRED_UI_MODULES = (
    "kx_manager.ui",
    "kx_manager.ui.app",
    "kx_manager.ui.pages",
    "kx_manager.ui.state",
    "kx_manager.ui.components",
    "kx_manager.ui.actions",
    "kx_manager.ui.forms",
    "kx_manager.ui.render",
)

OPTIONAL_UI_MODULES = (
    "kx_manager.ui.streamlit_app",
)

REQUIRED_MANAGER_SERVICE_MODULES = (
    "kx_manager.services.builder",
    "kx_manager.services.targets",
    "kx_manager.services.deploy",
)

REQUIRED_PAGE_ROUTES = (
    "/ui",
    "/ui/capsules",
    "/ui/instances",
    "/ui/security",
    "/ui/network",
    "/ui/backups",
    "/ui/restore",
    "/ui/logs",
    "/ui/health",
    "/ui/settings",
    "/ui/about",
    "/ui/targets",
)

REQUIRED_UI_ACTION_VALUES = (
    "check_manager",
    "check_agent",
    "select_source_folder",
    "select_capsule_output_folder",
    "build_capsule",
    "rebuild_capsule",
    "verify_capsule",
    "import_capsule",
    "list_capsules",
    "view_capsule",
    "create_instance",
    "update_instance",
    "start_instance",
    "stop_instance",
    "restart_instance",
    "instance_status",
    "view_logs",
    "view_health",
    "open_instance",
    "rollback_instance",
    "create_backup",
    "list_backups",
    "verify_backup",
    "restore_backup",
    "restore_backup_new",
    "test_restore_backup",
    "run_security_check",
    "set_network_profile",
    "disable_public_mode",
    "set_target_local",
    "set_target_intranet",
    "set_target_droplet",
    "set_target_temporary_public",
    "deploy_local",
    "deploy_intranet",
    "deploy_droplet",
    "check_droplet_agent",
    "copy_capsule_to_droplet",
    "start_droplet_instance",
    "open_manager_docs",
    "open_agent_docs",
)

REQUIRED_ACTION_ROUTE_VALUES = (
    "/ui/actions/check-manager",
    "/ui/actions/check-agent",
    "/ui/actions/select-source-folder",
    "/ui/actions/select-capsule-output-folder",
    "/ui/actions/build-capsule",
    "/ui/actions/rebuild-capsule",
    "/ui/actions/verify-capsule",
    "/ui/actions/import-capsule",
    "/ui/actions/list-capsules",
    "/ui/actions/view-capsule",
    "/ui/actions/create-instance",
    "/ui/actions/update-instance",
    "/ui/actions/start-instance",
    "/ui/actions/stop-instance",
    "/ui/actions/restart-instance",
    "/ui/actions/instance-status",
    "/ui/actions/view-logs",
    "/ui/actions/view-health",
    "/ui/actions/rollback-instance",
    "/ui/actions/create-backup",
    "/ui/actions/list-backups",
    "/ui/actions/verify-backup",
    "/ui/actions/restore-backup",
    "/ui/actions/restore-backup-new",
    "/ui/actions/test-restore-backup",
    "/ui/actions/run-security-check",
    "/ui/actions/set-network-profile",
    "/ui/actions/disable-public-mode",
    "/ui/actions/set-target-local",
    "/ui/actions/set-target-intranet",
    "/ui/actions/set-target-droplet",
    "/ui/actions/set-target-temporary-public",
    "/ui/actions/deploy-local",
    "/ui/actions/deploy-intranet",
    "/ui/actions/deploy-droplet",
    "/ui/actions/check-droplet-agent",
    "/ui/actions/copy-capsule-to-droplet",
    "/ui/actions/start-droplet-instance",
)

REQUIRED_LABELS = (
    "Check Manager",
    "Check Agent",
    "Select Source Folder",
    "Select Output Folder",
    "Build Capsule",
    "Rebuild Capsule",
    "Verify Capsule",
    "Import Capsule",
    "List Capsules",
    "View Capsule",
    "Create Instance",
    "Update Instance",
    "Start Instance",
    "Stop Instance",
    "Restart Instance",
    "Instance Status",
    "View Logs",
    "Instance Health",
    "Open Instance",
    "Rollback",
    "Create Backup",
    "List Backups",
    "Verify Backup",
    "Restore Backup",
    "Restore Backup New",
    "Test Restore Backup",
    "Run Security Check",
    "Set Network Profile",
    "Disable Public Mode",
    "Set Local Target",
    "Set Intranet Target",
    "Set Droplet Target",
    "Set Temporary Public Target",
    "Deploy Local",
    "Deploy Intranet",
    "Deploy Droplet",
    "Check Droplet Agent",
    "Copy Capsule to Droplet",
    "Start Droplet Instance",
    "Open Manager Docs",
    "Open Agent Docs",
)

REQUIRED_STATE_MODELS = (
    "CapsuleUiState",
    "SecurityCheckUiState",
    "SecurityUiState",
    "NetworkUiState",
    "BackupUiState",
    "InstanceUiState",
    "ManagerUiState",
    "TargetModeUiState",
    "DropletTargetUiState",
    "BuildTargetUiState",
)

REQUIRED_FORM_MODELS = (
    "BuildCapsuleForm",
    "VerifyCapsuleForm",
    "ImportCapsuleForm",
    "CreateInstanceForm",
    "UpdateInstanceForm",
    "InstanceActionForm",
    "LogsForm",
    "BackupForm",
    "RestoreForm",
    "RollbackForm",
    "NetworkProfileForm",
    "TargetModeForm",
    "DropletTargetForm",
)

REQUIRED_GUI_ACTION_RESULT_FIELDS = (
    "ok",
    "action",
    "message",
    "instance_id",
    "data",
    "stdout",
    "stderr",
    "returncode",
)

REQUIRED_BUILDER_FUNCTIONS = (
    "build_capsule",
    "verify_capsule",
)

REQUIRED_TARGET_FUNCTIONS = (
    "validate_target_config",
    "network_profile_for_target",
    "exposure_mode_for_target",
)

REQUIRED_DEPLOY_FUNCTIONS = (
    "deploy_local",
    "deploy_intranet",
    "deploy_droplet",
)

REQUIRED_TARGET_MODE_VALUES = (
    "local",
    "intranet",
    "temporary_public",
    "droplet",
)

FORBIDDEN_TARGET_MODE_VALUES = (
    "dev",
    "demo",
    "lan_private",
    "vps",
    "server",
    "production",
    "cloud",
    "public_server",
)


def test_required_ui_modules_import() -> None:
    for module_name in REQUIRED_UI_MODULES:
        module = importlib.import_module(module_name)
        assert isinstance(module, ModuleType), module_name


def test_optional_streamlit_app_module_is_isolated_if_present() -> None:
    for module_name in OPTIONAL_UI_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        assert isinstance(module, ModuleType), module_name


def test_required_manager_service_modules_import() -> None:
    for module_name in REQUIRED_MANAGER_SERVICE_MODULES:
        module = importlib.import_module(module_name)
        assert isinstance(module, ModuleType), module_name


def test_fastapi_ui_register_exists() -> None:
    app_module = importlib.import_module("kx_manager.ui.app")

    assert hasattr(app_module, "register")
    assert callable(app_module.register)

    signature = inspect.signature(app_module.register)
    assert "app" in signature.parameters


def test_fastapi_ui_import_does_not_require_streamlit(monkeypatch: pytest.MonkeyPatch) -> None:
    """FastAPI GUI import must not import or require Streamlit."""

    real_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "streamlit" or name.startswith("streamlit."):
            raise ModuleNotFoundError("streamlit intentionally blocked by contract test")
        return real_import(name, *args, **kwargs)

    for module_name in list(sys.modules):
        if module_name.startswith("kx_manager.ui.app"):
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    app_module = importlib.import_module("kx_manager.ui.app")
    assert callable(app_module.register)


def test_required_page_routes_exist_in_pages_contract() -> None:
    pages = importlib.import_module("kx_manager.ui.pages")
    route_values = _collect_route_values(pages, candidate_names=("UI_PAGE_ROUTES", "PAGE_ROUTES", "PAGES"))

    missing = set(REQUIRED_PAGE_ROUTES) - route_values
    assert not missing, f"Missing required page routes: {sorted(missing)}"

    non_ui_routes = {route for route in route_values if route and not route.startswith("/ui")}
    assert not non_ui_routes, f"All GUI page routes must start with /ui: {sorted(non_ui_routes)}"


def test_required_action_routes_exist_in_pages_contract() -> None:
    pages = importlib.import_module("kx_manager.ui.pages")
    route_values = _collect_route_values(
        pages,
        candidate_names=("UI_ACTION_ROUTES", "ACTION_ROUTES", "ACTIONS"),
    )

    missing = set(REQUIRED_ACTION_ROUTE_VALUES) - route_values
    assert not missing, f"Missing required action routes: {sorted(missing)}"

    non_action_routes = {
        route
        for route in route_values
        if route and not route.startswith("/ui/actions")
    }
    assert not non_action_routes, (
        "All GUI action routes must start with /ui/actions: "
        f"{sorted(non_action_routes)}"
    )


def test_uiaction_values_match_contract() -> None:
    pages = importlib.import_module("kx_manager.ui.pages")

    assert hasattr(pages, "UiAction"), "kx_manager.ui.pages must expose UiAction"

    values = set(_enum_values(pages.UiAction))
    expected = set(REQUIRED_UI_ACTION_VALUES)

    assert values == expected, (
        "UiAction values must match the GUI action contract. "
        f"Missing={sorted(expected - values)} Extra={sorted(values - expected)}"
    )


def test_uiaction_count_matches_explicit_contract_list() -> None:
    pages = importlib.import_module("kx_manager.ui.pages")
    values = tuple(_enum_values(pages.UiAction))

    assert len(values) == len(REQUIRED_UI_ACTION_VALUES)
    assert len(set(values)) == len(values), "UiAction values must be unique"


def test_all_required_labels_exist() -> None:
    pages = importlib.import_module("kx_manager.ui.pages")
    labels = _collect_label_values(pages)

    missing = set(REQUIRED_LABELS) - labels
    assert not missing, f"Missing required GUI labels: {sorted(missing)}"


def test_every_uiaction_has_a_label() -> None:
    pages = importlib.import_module("kx_manager.ui.pages")
    actions = set(_enum_values(pages.UiAction))
    label_keys = _collect_mapping_keys(
        pages,
        candidate_names=("UI_ACTION_LABELS", "ACTION_LABELS", "LABELS"),
    )

    missing = actions - label_keys
    assert not missing, f"Every UiAction must have a label. Missing: {sorted(missing)}"


def test_required_state_models_exist() -> None:
    state = importlib.import_module("kx_manager.ui.state")

    for model_name in REQUIRED_STATE_MODELS:
        assert hasattr(state, model_name), f"Missing state model: {model_name}"


def test_required_form_models_exist() -> None:
    forms = importlib.import_module("kx_manager.ui.forms")

    for model_name in REQUIRED_FORM_MODELS:
        assert hasattr(forms, model_name), f"Missing form model: {model_name}"


def test_gui_action_result_contract_exists() -> None:
    actions = importlib.import_module("kx_manager.ui.actions")

    assert hasattr(actions, "GuiActionResult")
    result_model = actions.GuiActionResult

    field_names = _dataclass_or_annotation_fields(result_model)
    missing = set(REQUIRED_GUI_ACTION_RESULT_FIELDS) - field_names

    assert not missing, f"GuiActionResult missing fields: {sorted(missing)}"


def test_dispatch_gui_action_contract_exists() -> None:
    actions = importlib.import_module("kx_manager.ui.actions")

    assert hasattr(actions, "dispatch_gui_action")
    assert callable(actions.dispatch_gui_action)

    signature = inspect.signature(actions.dispatch_gui_action)
    assert "action" in signature.parameters
    assert "payload" in signature.parameters


def test_unknown_gui_action_is_rejected() -> None:
    actions = importlib.import_module("kx_manager.ui.actions")

    if not hasattr(actions, "is_known_gui_action"):
        pytest.skip("is_known_gui_action helper not implemented; covered by dispatcher tests.")

    assert actions.is_known_gui_action("definitely_not_a_real_action") is False


def test_builder_service_contract_exists() -> None:
    builder = importlib.import_module("kx_manager.services.builder")

    for function_name in REQUIRED_BUILDER_FUNCTIONS:
        assert hasattr(builder, function_name), f"Missing builder function: {function_name}"
        assert callable(getattr(builder, function_name))


def test_target_service_contract_exists() -> None:
    targets = importlib.import_module("kx_manager.services.targets")

    for function_name in REQUIRED_TARGET_FUNCTIONS:
        assert hasattr(targets, function_name), f"Missing target function: {function_name}"
        assert callable(getattr(targets, function_name))


def test_deploy_service_contract_exists() -> None:
    deploy = importlib.import_module("kx_manager.services.deploy")

    for function_name in REQUIRED_DEPLOY_FUNCTIONS:
        assert hasattr(deploy, function_name), f"Missing deploy function: {function_name}"
        assert callable(getattr(deploy, function_name))


def test_target_mode_values_match_contract() -> None:
    targets = importlib.import_module("kx_manager.services.targets")

    assert hasattr(targets, "TargetMode"), "kx_manager.services.targets must expose TargetMode"

    values = set(_enum_values(targets.TargetMode))
    expected = set(REQUIRED_TARGET_MODE_VALUES)

    assert values == expected, (
        "TargetMode values must be canonical. "
        f"Missing={sorted(expected - values)} Extra={sorted(values - expected)}"
    )


def test_forbidden_target_mode_values_are_not_present() -> None:
    targets = importlib.import_module("kx_manager.services.targets")
    values = set(_enum_values(targets.TargetMode))

    forbidden = values.intersection(FORBIDDEN_TARGET_MODE_VALUES)
    assert not forbidden, f"Forbidden target mode values found: {sorted(forbidden)}"


def test_target_profile_and_exposure_maps_are_canonical() -> None:
    targets = importlib.import_module("kx_manager.services.targets")

    profile_map = getattr(targets, "TARGET_PROFILE_MAP", None)
    exposure_map = getattr(targets, "TARGET_DEFAULT_EXPOSURE_MAP", None)

    assert isinstance(profile_map, Mapping), "TARGET_PROFILE_MAP must be a mapping"
    assert isinstance(exposure_map, Mapping), "TARGET_DEFAULT_EXPOSURE_MAP must be a mapping"

    profile_values = {_string_value(value) for value in profile_map.values()}
    exposure_values = {_string_value(value) for value in exposure_map.values()}

    assert "local_only" in profile_values
    assert "intranet_private" in profile_values
    assert "public_temporary" in profile_values
    assert "public_vps" in profile_values

    assert "private" in exposure_values
    assert "temporary_tunnel" in exposure_values
    assert "public" in exposure_values


def test_register_adds_required_routes_when_fastapi_available() -> None:
    fastapi = pytest.importorskip("fastapi")

    app_module = importlib.import_module("kx_manager.ui.app")
    app = fastapi.FastAPI()

    app_module.register(app)

    registered_routes = {
        route.path
        for route in app.routes
        if hasattr(route, "path")
    }

    missing = set(REQUIRED_PAGE_ROUTES) - registered_routes
    assert not missing, f"register(app) did not register page routes: {sorted(missing)}"


def test_registered_routes_are_local_ui_routes_when_fastapi_available() -> None:
    fastapi = pytest.importorskip("fastapi")

    app_module = importlib.import_module("kx_manager.ui.app")
    app = fastapi.FastAPI()

    app_module.register(app)

    gui_routes = {
        route.path
        for route in app.routes
        if hasattr(route, "path") and route.path.startswith("/ui")
    }

    assert gui_routes, "register(app) must add /ui routes"
    assert all(route.startswith("/ui") for route in gui_routes)


def test_no_shell_true_in_ui_or_manager_services() -> None:
    modules = [
        *REQUIRED_UI_MODULES,
        *REQUIRED_MANAGER_SERVICE_MODULES,
    ]

    offenders: list[str] = []

    for module_name in modules:
        module = importlib.import_module(module_name)
        source = _safe_getsource(module)

        if "shell=True" in source or "shell = True" in source:
            offenders.append(module_name)

    assert not offenders, f"shell=True is forbidden in GUI/services: {offenders}"


def test_no_streamlit_import_in_fastapi_ui_modules() -> None:
    modules = (
        "kx_manager.ui.app",
        "kx_manager.ui.actions",
        "kx_manager.ui.forms",
        "kx_manager.ui.render",
        "kx_manager.ui.pages",
        "kx_manager.ui.state",
        "kx_manager.ui.components",
    )

    offenders: list[str] = []

    for module_name in modules:
        module = importlib.import_module(module_name)
        source = _safe_getsource(module)

        if "import streamlit" in source or "from streamlit" in source:
            offenders.append(module_name)

    assert not offenders, f"FastAPI GUI modules must not import Streamlit: {offenders}"


def test_ui_action_execution_uses_manager_client_or_service_wrappers() -> None:
    actions = importlib.import_module("kx_manager.ui.actions")
    source = _safe_getsource(actions)

    allowed_references = (
        "KonnaxionAgentClient",
        "kx_manager.client",
        "services.builder",
        "services.targets",
        "services.deploy",
        "build_capsule",
        "verify_capsule",
        "deploy_local",
        "deploy_intranet",
        "deploy_droplet",
    )

    assert any(reference in source for reference in allowed_references), (
        "UI actions must dispatch through Manager client or approved service wrappers."
    )


def test_component_module_does_not_execute_actions() -> None:
    components = importlib.import_module("kx_manager.ui.components")
    source = _safe_getsource(components)

    forbidden_terms = (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "dispatch_gui_action(",
    )

    offenders = [term for term in forbidden_terms if term in source]
    assert not offenders, f"components.py must render only, not execute actions: {offenders}"


def test_render_module_escapes_html_or_uses_safe_html_helpers() -> None:
    render = importlib.import_module("kx_manager.ui.render")
    source = _safe_getsource(render)

    assert (
        "html.escape" in source
        or "markupsafe" in source.lower()
        or "escape(" in source
    ), "render.py must escape HTML by default or use a safe escaping helper."


def _enum_values(enum_or_iterable: Any) -> tuple[str, ...]:
    if inspect.isclass(enum_or_iterable) and issubclass(enum_or_iterable, Enum):
        return tuple(str(item.value) for item in enum_or_iterable)

    if isinstance(enum_or_iterable, Mapping):
        return tuple(str(key) for key in enum_or_iterable.keys())

    if isinstance(enum_or_iterable, Iterable) and not isinstance(enum_or_iterable, (str, bytes)):
        return tuple(str(item) for item in enum_or_iterable)

    raise TypeError(f"Cannot collect enum values from {enum_or_iterable!r}")


def _string_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _collect_route_values(module: ModuleType, *, candidate_names: tuple[str, ...]) -> set[str]:
    values: set[str] = set()

    for name in candidate_names:
        obj = getattr(module, name, None)
        values.update(_extract_routes(obj))

    return values


def _extract_routes(obj: Any) -> set[str]:
    if obj is None:
        return set()

    if isinstance(obj, str):
        return {obj}

    if isinstance(obj, Mapping):
        routes: set[str] = set()

        for key, value in obj.items():
            routes.update(_extract_routes(key))
            routes.update(_extract_routes(value))

        return routes

    if isinstance(obj, Iterable):
        routes = set()

        for item in obj:
            routes.update(_extract_routes(item))

        return routes

    routes = set()

    for attr_name in ("route", "path", "url", "href"):
        value = getattr(obj, attr_name, None)
        if isinstance(value, str):
            routes.add(value)

    return routes


def _collect_label_values(module: ModuleType) -> set[str]:
    labels: set[str] = set()

    for name in ("UI_ACTION_LABELS", "ACTION_LABELS", "LABELS", "PAGE_LABELS"):
        obj = getattr(module, name, None)

        if isinstance(obj, Mapping):
            labels.update(str(value) for value in obj.values())
        elif isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
            labels.update(str(value) for value in obj)

    return labels


def _collect_mapping_keys(module: ModuleType, *, candidate_names: tuple[str, ...]) -> set[str]:
    keys: set[str] = set()

    for name in candidate_names:
        obj = getattr(module, name, None)

        if isinstance(obj, Mapping):
            keys.update(_string_value(key) for key in obj.keys())

    return keys


def _dataclass_or_annotation_fields(model: Any) -> set[str]:
    annotations = getattr(model, "__annotations__", None)
    if isinstance(annotations, Mapping):
        return set(str(key) for key in annotations)

    dataclass_fields = getattr(model, "__dataclass_fields__", None)
    if isinstance(dataclass_fields, Mapping):
        return set(str(key) for key in dataclass_fields)

    model_fields = getattr(model, "model_fields", None)
    if isinstance(model_fields, Mapping):
        return set(str(key) for key in model_fields)

    fields = getattr(model, "__fields__", None)
    if isinstance(fields, Mapping):
        return set(str(key) for key in fields)

    return set()


def _safe_getsource(module: ModuleType) -> str:
    try:
        return inspect.getsource(module)
    except (OSError, TypeError):
        file_value = getattr(module, "__file__", None)
        if not file_value:
            return ""

        path = Path(file_value)
        if not path.exists():
            return ""

        return path.read_text(encoding="utf-8")