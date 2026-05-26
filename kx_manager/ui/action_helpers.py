# kx_manager/ui/action_helpers.py

"""Shared helper functions for Konnaxion Manager GUI actions.

This module contains reusable, side-effect-limited utilities used by:

- kx_manager.ui.action_dispatch
- kx_manager.ui.action_backends

It does not define the public dispatcher, action constants, or backend handlers.
"""

from __future__ import annotations

import importlib
import inspect
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

try:
    from kx_manager.ui.action_models import GuiActionResult, JsonDict
except Exception:  # pragma: no cover - staged split compatibility
    JsonDict = dict[str, Any]

    @dataclass(slots=True)
    class GuiActionResult:  # type: ignore[no-redef]
        ok: bool
        action: str
        message: str
        instance_id: str | None = None
        data: JsonDict = field(default_factory=dict)
        stdout: str | None = None
        stderr: str | None = None
        returncode: int | None = None

        def to_dict(self) -> JsonDict:
            return {
                "ok": self.ok,
                "action": self.action,
                "message": self.message,
                "instance_id": self.instance_id,
                "data": _json_safe(self.data),
                "stdout": self.stdout,
                "stderr": self.stderr,
                "returncode": self.returncode,
            }


def _normalize_payload(payload: JsonDict) -> JsonDict:
    """Apply final dispatcher-level payload normalizations."""

    normalized = dict(payload)

    if "source_backup_id" not in normalized:
        for key in ("from_backup_id", "backup_id"):
            if normalized.get(key):
                normalized["source_backup_id"] = normalized[key]
                break

    return normalized


def _action_value(action: Any) -> str:
    """Return the string value for an enum-like or raw action."""

    value = getattr(action, "value", action)
    return str(value).strip()


def _payload_instance_id(payload: Mapping[str, Any]) -> str | None:
    """Return the best-known instance ID from a payload."""

    value = payload.get("instance_id") or payload.get("KX_INSTANCE_ID")
    return str(value) if value not in (None, "") else None


def _require_text(payload: Mapping[str, Any], *names: str) -> str:
    """Return the first non-empty text value or raise ValueError."""

    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return str(value).strip()

    joined = ", ".join(names)
    raise ValueError(f"Missing required field: {joined}")


def _optional_text(payload: Mapping[str, Any], *names: str) -> str | None:
    """Return the first non-empty text value, if present."""

    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return str(value).strip()

    return None


def _truthy(value: Any) -> bool:
    """Return whether a submitted value means true/confirmed."""

    if isinstance(value, bool):
        return value

    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "checked",
        "confirmed",
    }


def _bool(value: Any, *, default: bool = False) -> bool:
    """Coerce a submitted value to bool."""

    if value is None or value == "":
        return default

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "checked",
        "confirmed",
    }


def _int(value: Any, *, default: int) -> int:
    """Coerce a submitted value to int with fallback."""

    if value is None or value == "":
        return default

    if isinstance(value, bool):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _target_message(target_mode: str) -> str:
    """Return the success message for a target mode."""

    return {
        "local": "Local target configured.",
        "intranet": "Intranet target configured.",
        "temporary_public": "Temporary public target configured.",
        "droplet": "Droplet target configured.",
    }[target_mode]


def _missing_backend(action: str, backend: str) -> GuiActionResult:
    """Return a standard result for a missing optional backend."""

    return GuiActionResult(
        ok=False,
        action=action,
        message=f"Required backend is not available: {backend}",
        data={"backend": backend},
    )


def _manager_base_url() -> str:
    """Return the configured Manager API base URL."""

    if os.getenv("KX_MANAGER_URL"):
        return os.environ["KX_MANAGER_URL"].rstrip("/")

    host = os.getenv("KX_MANAGER_HOST", "127.0.0.1")
    port = os.getenv("KX_MANAGER_PORT", "8714")
    scheme = os.getenv("KX_MANAGER_SCHEME", "http")
    return f"{scheme}://{host}:{port}"


def _agent_base_url() -> str:
    """Return the configured Agent API base URL."""

    if os.getenv("KX_AGENT_URL"):
        return os.environ["KX_AGENT_URL"].rstrip("/")

    host = os.getenv("KX_AGENT_HOST", "127.0.0.1")
    port = os.getenv("KX_AGENT_PORT", "8765")
    scheme = os.getenv("KX_AGENT_SCHEME", "http")
    prefix = os.getenv("KX_AGENT_API_PREFIX", "/v1").strip() or "/v1"
    return f"{scheme}://{host}:{port}/{prefix.strip('/')}"


def _http_timeout_seconds() -> float:
    """Return the configured timeout for Manager/Agent HTTP calls."""

    raw = (
        os.getenv("KX_AGENT_TIMEOUT_SECONDS")
        or os.getenv("KX_MANAGER_TIMEOUT_SECONDS")
        or "30.0"
    )

    try:
        return float(raw)
    except ValueError:
        return 30.0


def _query_string(params: Mapping[str, Any]) -> str:
    """Return a URL query string for non-empty params."""

    clean = {
        key: str(value)
        for key, value in params.items()
        if value not in (None, "")
    }

    if not clean:
        return ""

    return "?" + urlencode(clean)


def _query_string_without_question(query: str, *remove_keys: str) -> str:
    """Return query string minus selected keys."""

    if not query:
        return ""

    raw = query[1:] if query.startswith("?") else query
    if not raw:
        return ""

    pairs: list[str] = []
    remove = set(remove_keys)

    for fragment in raw.split("&"):
        if not fragment:
            continue

        key = fragment.split("=", 1)[0]
        if key in remove:
            continue

        pairs.append(fragment)

    return "?" + "&".join(pairs) if pairs else ""


async def _http_json_request(
    method: str,
    url: str,
    payload: Mapping[str, Any] | None = None,
) -> JsonDict:
    """Perform an HTTP request and normalize the response body to a dict."""

    async with httpx.AsyncClient(timeout=_http_timeout_seconds()) as client:
        try:
            response = await client.request(
                method.upper(),
                url,
                json=(
                    dict(payload or {})
                    if payload is not None and method.upper() != "GET"
                    else None
                ),
            )
        except httpx.HTTPError as exc:
            return {"ok": False, "message": str(exc), "url": url}

    try:
        body: Any = response.json() if response.content else {}
    except ValueError:
        body = {"body": response.text}

    if isinstance(body, Mapping):
        result = dict(body)
    else:
        result = {"items": body}

    result.setdefault("ok", 200 <= response.status_code < 300)
    result.setdefault("status_code", response.status_code)
    result.setdefault("url", url)

    if response.is_error:
        result["ok"] = False
        detail = result.get("detail")

        if isinstance(detail, Mapping):
            result.setdefault(
                "message",
                detail.get("message")
                or detail.get("error")
                or detail.get("detail")
                or f"HTTP {response.status_code}",
            )
        else:
            result.setdefault(
                "message",
                detail or result.get("error") or f"HTTP {response.status_code}",
            )

    return result


async def _manager_request_first(
    *,
    action: str,
    payload: Mapping[str, Any],
    attempts: Sequence[tuple[str, str]],
    success_message: str,
    failure_message: str,
) -> GuiActionResult:
    """Try Manager API endpoints in order and return the first success."""

    last: JsonDict | None = None
    failures: list[JsonDict] = []

    for method, path in attempts:
        url = _manager_base_url().rstrip("/") + path
        result = await _http_json_request(
            method,
            url,
            payload if method.upper() != "GET" else None,
        )
        last = result

        if result.get("ok") is True:
            return _result_from_backend(
                action=action,
                outcome=result,
                payload=payload,
                default_message=success_message,
                ok_default=True,
            )

        failures.append(result)

    final = dict(last or {})
    final.setdefault("message", failure_message)

    if failures:
        final["attempts"] = failures

    return _result_from_backend(
        action=action,
        outcome=final,
        payload=payload,
        default_message=failure_message,
        ok_default=False,
    )


async def _validate_target_config(config: Mapping[str, Any]) -> JsonDict:
    """Validate target config through the optional target service module."""

    targets = _try_import_module("kx_manager.services.targets")

    if targets is None:
        return {}

    data: JsonDict = {}
    target_config: Any = None

    build = getattr(targets, "build_target_config", None)
    if callable(build):
        target_config = await _call_callable_with_best_effort(build, config)

    if target_config is None:
        request_class = (
            "DropletTargetConfig"
            if str(config.get("target_mode")) == "droplet"
            else "TargetConfig"
        )
        target_config = _request_object(targets, request_class, config)

    validate = getattr(targets, "validate_target_config", None)
    if callable(validate) and target_config is not None:
        await _call_callable_with_best_effort(
            validate,
            {},
            preferred_args=(target_config,),
        )

    summary = getattr(targets, "target_summary", None)
    if callable(summary) and target_config is not None:
        value = await _call_callable_with_best_effort(
            summary,
            {},
            preferred_args=(target_config,),
        )
        if isinstance(value, Mapping):
            data.update(_json_safe(value))

    profile_for_target = getattr(targets, "network_profile_for_target", None)
    if callable(profile_for_target):
        profile = await _call_callable_with_best_effort(
            profile_for_target,
            {"target_mode": config["target_mode"]},
            preferred_args=(config["target_mode"],),
        )
        data["network_profile"] = _enum_value(profile)

    exposure_for_target = getattr(targets, "exposure_mode_for_target", None)
    if callable(exposure_for_target):
        exposure = await _call_callable_with_best_effort(
            exposure_for_target,
            {"target_mode": config["target_mode"]},
            preferred_args=(config["target_mode"],),
        )

        if config["target_mode"] == "intranet" and config.get("exposure_mode") == "lan":
            data["exposure_mode"] = "lan"
        else:
            data["exposure_mode"] = _enum_value(exposure)

    return data


async def _call_service_function(
    function: Callable[..., Any],
    payload: Mapping[str, Any],
    *,
    request_module: Any | None = None,
    request_class_name: str | None = None,
) -> Any:
    """Call a backend service function using its request class when available."""

    preferred_args: tuple[Any, ...] = ()

    if request_module is not None and request_class_name:
        request_object = _request_object(request_module, request_class_name, payload)
        if request_object is not None:
            preferred_args = (request_object,)

    return await _call_callable_with_best_effort(
        function,
        payload,
        preferred_args=preferred_args,
    )


async def _call_callable_with_best_effort(
    function: Callable[..., Any],
    payload: Mapping[str, Any],
    *,
    preferred_args: Sequence[Any] = (),
) -> Any:
    """Call a callable using several compatible argument shapes."""

    attempts: list[tuple[tuple[Any, ...], JsonDict]] = []

    if preferred_args:
        attempts.append((tuple(preferred_args), {}))

    attempts.append(((), _filtered_kwargs(function, payload)))
    attempts.append(((dict(payload),), {}))
    attempts.append(((), dict(payload)))
    attempts.append(((), {}))

    errors: list[str] = []

    for args, kwargs in attempts:
        try:
            result = function(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result
        except TypeError as exc:
            errors.append(str(exc))
            continue

    raise TypeError("; ".join(errors) or f"Could not call backend function {function!r}")


def _filtered_kwargs(
    function: Callable[..., Any],
    payload: Mapping[str, Any],
) -> JsonDict:
    """Filter payload keys to match a callable signature."""

    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return dict(payload)

    parameters = list(signature.parameters.values())

    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return dict(payload)

    allowed = {
        parameter.name
        for parameter in parameters
        if parameter.kind
        in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    }

    return {key: value for key, value in payload.items() if key in allowed}


def _request_object(
    module: Any,
    class_name: str,
    payload: Mapping[str, Any],
) -> Any | None:
    """Build a request object from a service module class, when available."""

    request_class = getattr(module, class_name, None)

    if request_class is None:
        return None

    data = dict(payload)

    if hasattr(request_class, "__dataclass_fields__"):
        allowed = set(request_class.__dataclass_fields__)
        unknown = {key: value for key, value in data.items() if key not in allowed}
        data = {key: value for key, value in data.items() if key in allowed}

        if "extra" in allowed and "extra" not in data and unknown:
            data["extra"] = unknown

    try:
        return request_class(**data)
    except TypeError:
        try:
            return request_class(dict(payload))
        except TypeError:
            return None


def _result_from_backend(
    *,
    action: str,
    outcome: Any,
    payload: Mapping[str, Any],
    default_message: str,
    ok_default: bool = True,
) -> GuiActionResult:
    """Normalize any backend result shape into GuiActionResult."""

    if isinstance(outcome, GuiActionResult):
        return outcome

    data = _normalize_backend_outcome(outcome)
    stdout = _pop_optional_str(data, "stdout")
    stderr = _pop_optional_str(data, "stderr")
    returncode = _pop_optional_int(data, "returncode")

    ok = bool(data.pop("ok", ok_default))

    if returncode not in (None, 0):
        ok = False

    message = str(
        data.pop(
            "message",
            data.pop("detail", default_message),
        )
    )

    instance_id = (
        data.get("instance_id")
        or data.get("KX_INSTANCE_ID")
        or _payload_instance_id(payload)
    )

    if instance_id is not None:
        instance_id = str(instance_id)

    return GuiActionResult(
        ok=ok,
        action=action,
        message=message,
        instance_id=instance_id,
        data=_json_safe(data),
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
    )


def _normalize_backend_outcome(outcome: Any) -> JsonDict:
    """Normalize backend outputs into a JSON-like dict."""

    if outcome is None:
        return {}

    if isinstance(outcome, GuiActionResult):
        return outcome.to_dict()

    if isinstance(outcome, Mapping):
        return dict(outcome)

    if is_dataclass(outcome):
        return _json_safe(asdict(outcome))

    model_dump = getattr(outcome, "model_dump", None)
    if callable(model_dump):
        value = model_dump()
        return _json_safe(value if isinstance(value, Mapping) else {"result": value})

    dict_method = getattr(outcome, "dict", None)
    if callable(dict_method):
        value = dict_method()
        return _json_safe(value if isinstance(value, Mapping) else {"result": value})

    if isinstance(outcome, (list, tuple)):
        return {"items": _json_safe(list(outcome))}

    return {"result": _json_safe(outcome)}


def _json_safe(value: Any) -> Any:
    """Return a JSON-compatible representation of common Python objects."""

    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "value"):
        return value.value

    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)

    if is_dataclass(value):
        return _json_safe(asdict(value))

    return value


def _pop_optional_str(data: JsonDict, key: str) -> str | None:
    """Pop an optional string field from a dict."""

    value = data.pop(key, None)
    return None if value is None else str(value)


def _pop_optional_int(data: JsonDict, key: str) -> int | None:
    """Pop an optional int field from a dict."""

    value = data.pop(key, None)

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _enum_value(value: Any) -> Any:
    """Return enum.value for enum-like values."""

    return getattr(value, "value", value)


def _import_module(module_name: str) -> Any:
    """Import and return a module by name."""

    return importlib.import_module(module_name)


def _try_import_module(module_name: str) -> Any | None:
    """Import a module by name, returning None on failure."""

    try:
        return _import_module(module_name)
    except Exception:
        return None


__all__ = [
    "_action_value",
    "_agent_base_url",
    "_bool",
    "_call_callable_with_best_effort",
    "_call_service_function",
    "_enum_value",
    "_filtered_kwargs",
    "_http_json_request",
    "_http_timeout_seconds",
    "_import_module",
    "_int",
    "_json_safe",
    "_manager_base_url",
    "_manager_request_first",
    "_missing_backend",
    "_normalize_backend_outcome",
    "_normalize_payload",
    "_optional_text",
    "_payload_instance_id",
    "_pop_optional_int",
    "_pop_optional_str",
    "_query_string",
    "_query_string_without_question",
    "_request_object",
    "_require_text",
    "_result_from_backend",
    "_target_message",
    "_truthy",
    "_try_import_module",
    "_validate_target_config",
]