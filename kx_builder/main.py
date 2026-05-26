"""
Konnaxion Capsule Builder CLI entrypoint.

This module owns developer-side capsule commands. It should not perform Agent
runtime actions such as starting instances, changing firewall rules, or running
Docker Compose stacks. Its job is to build and verify signed .kxcap artifacts.

Canonical public commands implemented here:
- kx-builder capsule build
- kx-builder capsule verify

The implementation is dependency-light and uses argparse so it can run during
bootstrap before optional CLI frameworks are installed.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    BUILDER_NAME,
    CAPSULE_EXTENSION,
    CAPSULE_FILENAME_PATTERN,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_CHANNEL,
    DEFAULT_NETWORK_PROFILE,
    PARAM_VERSION,
)
from kx_shared.validation import (
    ValidationFailed,
    ValidationIssue,
    raise_if_issues,
    validate_capsule_filename,
    validate_capsule_id,
    validate_capsule_version,
    validate_network_profile,
)


@dataclass(frozen=True, slots=True)
class BuildRequest:
    """Normalized build request from CLI args."""

    source_dir: Path
    output: Path
    channel: str
    capsule_id: str
    capsule_version: str
    profile: str
    app_version: str
    param_version: str
    sign: bool
    verify: bool
    force: bool
    signing_key_file: Path | None = None
    signing_key_password: str | None = None
    signing_key_password_file: Path | None = None
    public_key_file: Path | None = None
    require_real_signature: bool = False
    require_signature_verifier: bool = False


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Structured build result suitable for JSON output."""

    ok: bool
    output: str
    capsule_id: str
    capsule_version: str
    app_version: str
    param_version: str
    message: str = ""


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """Structured verify result suitable for JSON output."""

    ok: bool
    capsule_path: str
    message: str = ""
    issues: tuple[Mapping[str, Any], ...] = ()
    errors: tuple[Mapping[str, Any], ...] = ()
    warnings: tuple[Mapping[str, Any], ...] = ()
    checks: tuple[Mapping[str, Any], ...] = ()
    capsule_file: str | None = None
    capsule_id: str | None = None
    capsule_version: str | None = None
    app_version: str | None = None
    param_version: str | None = None
    manifest: Mapping[str, Any] | None = None
    strict: bool = False


class BuilderCliError(RuntimeError):
    """User-facing CLI error."""

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        self.exit_code = exit_code
        super().__init__(message)


def build_capsule(request: BuildRequest) -> BuildResult:
    """Build a Konnaxion Capsule through kx_builder.package.build_package()."""

    _validate_build_request(request)

    try:
        from kx_builder.package import build_package  # type: ignore
    except ImportError as exc:
        raise BuilderCliError(
            "kx_builder.package.build_package is not available. "
            "Update kx_builder/package.py so it exposes build_package(...).",
            exit_code=3,
        ) from exc

    result = _call_build_package(build_package, request)
    return _normalize_build_result(request, result)


def verify_capsule(
    capsule_path: Path,
    *,
    strict: bool = False,
    public_key_file: Path | None = None,
    require_signature_verifier: bool = False,
) -> VerifyResult:
    """Verify a Konnaxion Capsule using Builder verifier first, Agent verifier second."""

    issues = validate_capsule_filename(capsule_path.name)
    if issues:
        if strict:
            raise ValidationFailed(issues)
        return _verify_result_from_validation_issues(
            capsule_path,
            "Invalid capsule filename.",
            issues,
            strict=strict,
        )

    if not capsule_path.exists():
        issue = ValidationIssue(
            code="capsule_not_found",
            message=f"Capsule file does not exist: {capsule_path}",
            field="capsule_path",
        )
        if strict:
            raise ValidationFailed((issue,))
        return _verify_result_from_validation_issues(
            capsule_path,
            issue.message,
            (issue,),
            strict=strict,
        )

    try:
        from kx_builder.verify import verify_capsule_file  # type: ignore
    except ImportError:
        verify_capsule_file = None

    if verify_capsule_file is not None:
        result = _call_verify_function(
            verify_capsule_file,
            capsule_path,
            strict=strict,
            public_key_file=public_key_file,
            require_signature_verifier=require_signature_verifier,
        )
        return _normalize_verify_result(capsule_path, result, strict=strict)

    try:
        from kx_agent.capsules.verifier import verify_capsule as agent_verify_capsule
    except ImportError as exc:
        raise BuilderCliError(
            "No capsule verifier is available. Implement "
            "kx_builder.verify.verify_capsule_file(...) or provide "
            "kx_agent.capsules.verifier.verify_capsule(...).",
            exit_code=3,
        ) from exc

    result = _call_verify_function(
        agent_verify_capsule,
        capsule_path,
        strict=strict,
        public_key_file=public_key_file,
        require_signature_verifier=require_signature_verifier,
    )
    return _normalize_verify_result(capsule_path, result, strict=strict)


def create_parser() -> argparse.ArgumentParser:
    """Create the argparse CLI parser."""

    parser = argparse.ArgumentParser(
        prog="kx-builder",
        description=f"{BUILDER_NAME} command-line entrypoint.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )

    subparsers = parser.add_subparsers(dest="command_group", required=True)

    capsule = subparsers.add_parser(
        "capsule",
        help="Build or verify Konnaxion Capsule artifacts.",
    )
    capsule_sub = capsule.add_subparsers(dest="capsule_command", required=True)

    build = capsule_sub.add_parser(
        "build",
        help="Build a signed Konnaxion Capsule.",
    )
    build.add_argument(
        "--source-dir",
        default=".",
        type=Path,
        help="Source tree or prepared capsule staging directory to package.",
    )
    build.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Output .kxcap path. Defaults to {CAPSULE_FILENAME_PATTERN}.",
    )
    build.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Capsule channel, for example demo, intranet, or release.",
    )
    build.add_argument(
        "--capsule-id",
        default=DEFAULT_CAPSULE_ID,
        help="Canonical capsule id.",
    )
    build.add_argument(
        "--version",
        dest="capsule_version",
        default=DEFAULT_CAPSULE_VERSION,
        help="Canonical capsule version.",
    )
    build.add_argument(
        "--profile",
        default=DEFAULT_NETWORK_PROFILE.value,
        help="Default network profile to include/target.",
    )
    build.add_argument(
        "--app-version",
        default=APP_VERSION,
        help="Konnaxion app version to write into the capsule manifest.",
    )
    build.add_argument(
        "--param-version",
        default=PARAM_VERSION,
        help="Konnaxion parameter/schema version to write into the capsule manifest.",
    )
    build.add_argument(
        "--unsigned",
        action="store_true",
        help="Build without signing. For local development only.",
    )
    build.add_argument(
        "--signing-key-file",
        type=Path,
        default=None,
        help="Ed25519 private key PEM used to create a cryptographic signature.",
    )
    build.add_argument(
        "--signing-key-password",
        default=None,
        help=(
            "Password for --signing-key-file. Prefer --signing-key-password-file "
            "outside local development."
        ),
    )
    build.add_argument(
        "--signing-key-password-file",
        type=Path,
        default=None,
        help="File containing the password for --signing-key-file.",
    )
    build.add_argument(
        "--require-real-signature",
        action="store_true",
        help="Fail the build unless a real signing key is provided and used.",
    )
    build.add_argument(
        "--public-key-file",
        type=Path,
        default=None,
        help="Ed25519 public key PEM used for post-build signature verification.",
    )
    build.add_argument(
        "--require-signature-verifier",
        action="store_true",
        help="Fail verification if no cryptographic signature verifier is available.",
    )
    build.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-build verification.",
    )
    build.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output file.",
    )

    verify = capsule_sub.add_parser(
        "verify",
        help="Verify a Konnaxion Capsule.",
    )
    verify.add_argument(
        "capsule",
        type=Path,
        help="Path to .kxcap file.",
    )
    verify.add_argument(
        "--strict",
        action="store_true",
        help="Fail on blocking issues and verifier warnings.",
    )
    verify.add_argument(
        "--public-key-file",
        type=Path,
        default=None,
        help="Ed25519 public key PEM used for cryptographic signature verification.",
    )
    verify.add_argument(
        "--require-signature-verifier",
        action="store_true",
        help="Fail if no cryptographic signature verifier is available.",
    )

    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run the Builder CLI and return a process exit code."""

    parser = create_parser()
    args = parser.parse_args(argv)

    try:
        if args.command_group == "capsule" and args.capsule_command == "build":
            request = _build_request_from_args(args)
            result = build_capsule(request)
            _print_result(result, json_output=args.json)
            return 0 if result.ok else 1

        if args.command_group == "capsule" and args.capsule_command == "verify":
            result = verify_capsule(
                args.capsule,
                strict=bool(args.strict),
                public_key_file=args.public_key_file,
                require_signature_verifier=bool(args.require_signature_verifier),
            )
            _print_result(result, json_output=args.json)
            return 0 if result.ok else 1

        parser.error("Unsupported command.")
        return 2

    except ValidationFailed as exc:
        _print_error("Validation failed.", issues=exc.issues, json_output=args.json)
        return 2

    except BuilderCliError as exc:
        _print_error(str(exc), json_output=args.json)
        return exc.exit_code

    except KeyboardInterrupt:
        _print_error("Interrupted.", json_output=args.json)
        return 130


def main() -> None:
    """Console-script entrypoint."""

    raise SystemExit(run())


def _build_request_from_args(args: argparse.Namespace) -> BuildRequest:
    output = args.output
    if output is None:
        filename = CAPSULE_FILENAME_PATTERN.format(
            channel=args.channel,
            date=_date_from_capsule_id(str(args.capsule_id)),
        )
        output = Path(filename)

    return BuildRequest(
        source_dir=Path(args.source_dir),
        output=Path(output),
        channel=str(args.channel),
        capsule_id=str(args.capsule_id),
        capsule_version=str(args.capsule_version),
        profile=str(args.profile),
        app_version=str(args.app_version),
        param_version=str(args.param_version),
        sign=not bool(args.unsigned),
        verify=not bool(args.no_verify),
        force=bool(args.force),
        signing_key_file=args.signing_key_file,
        signing_key_password=args.signing_key_password,
        signing_key_password_file=args.signing_key_password_file,
        public_key_file=args.public_key_file,
        require_real_signature=bool(args.require_real_signature),
        require_signature_verifier=bool(args.require_signature_verifier),
    )


def _validate_build_request(request: BuildRequest) -> None:
    issues: list[ValidationIssue] = []

    if not request.source_dir.exists() or not request.source_dir.is_dir():
        issues.append(
            ValidationIssue(
                code="source_dir_missing",
                message=f"Source directory does not exist: {request.source_dir}",
                field="source_dir",
            )
        )

    issues.extend(validate_capsule_filename(request.output.name))

    if request.output.suffix != CAPSULE_EXTENSION:
        issues.append(
            ValidationIssue(
                code="invalid_capsule_extension",
                message=f"Output file must end with {CAPSULE_EXTENSION}: {request.output}",
                field="output",
            )
        )

    if request.output.exists() and not request.force:
        issues.append(
            ValidationIssue(
                code="output_exists",
                message=f"Output file already exists. Use --force to overwrite: {request.output}",
                field="output",
            )
        )

    issues.extend(validate_capsule_id(request.capsule_id))
    issues.extend(validate_capsule_version(request.capsule_version))
    issues.extend(validate_network_profile(request.profile))

    if not request.app_version.strip():
        issues.append(
            ValidationIssue(
                code="app_version_missing",
                message="app_version cannot be empty.",
                field="app_version",
            )
        )

    if not request.param_version.strip():
        issues.append(
            ValidationIssue(
                code="param_version_missing",
                message="param_version cannot be empty.",
                field="param_version",
            )
        )

    if request.signing_key_password and request.signing_key_password_file:
        issues.append(
            ValidationIssue(
                code="duplicate_signing_key_password",
                message=(
                    "Use either --signing-key-password or "
                    "--signing-key-password-file, not both."
                ),
                field="signing_key_password",
            )
        )

    if request.signing_key_file and not request.signing_key_file.is_file():
        issues.append(
            ValidationIssue(
                code="signing_key_file_missing",
                message=f"Signing key file does not exist: {request.signing_key_file}",
                field="signing_key_file",
            )
        )

    if request.signing_key_password_file and not request.signing_key_password_file.is_file():
        issues.append(
            ValidationIssue(
                code="signing_key_password_file_missing",
                message=(
                    "Signing key password file does not exist: "
                    f"{request.signing_key_password_file}"
                ),
                field="signing_key_password_file",
            )
        )

    if request.public_key_file and not request.public_key_file.is_file():
        issues.append(
            ValidationIssue(
                code="public_key_file_missing",
                message=f"Public key file does not exist: {request.public_key_file}",
                field="public_key_file",
            )
        )

    if not request.sign:
        issues.append(
            ValidationIssue(
                code="unsigned_capsule",
                message=(
                    "Unsigned capsule build requested. This is allowed only for "
                    "local development."
                ),
                field="unsigned",
                blocking=False,
            )
        )

    if request.require_real_signature:
        if not request.sign:
            issues.append(
                ValidationIssue(
                    code="real_signature_requires_signing",
                    message="--require-real-signature cannot be used with --unsigned.",
                    field="require_real_signature",
                )
            )
        if not request.signing_key_file:
            issues.append(
                ValidationIssue(
                    code="signing_key_required",
                    message=(
                        "--require-real-signature requires --signing-key-file."
                    ),
                    field="signing_key_file",
                )
            )

    raise_if_issues(issues)


def _call_build_package(function: Any, request: BuildRequest) -> Any:
    password = _resolved_password(request)

    payload: dict[str, Any] = {
        "source_dir": request.source_dir,
        "output": request.output,
        "channel": request.channel,
        "capsule_id": request.capsule_id,
        "capsule_version": request.capsule_version,
        "profile": request.profile,
        "app_version": request.app_version,
        "param_version": request.param_version,
        "sign": request.sign,
        "verify": request.verify,
        "force": request.force,
        "signing_key_file": request.signing_key_file,
        "signing_key_password": password,
        "signing_key_password_file": request.signing_key_password_file,
        "public_key_file": request.public_key_file,
        "require_real_signature": request.require_real_signature,
        "require_signature_verifier": request.require_signature_verifier,
    }

    kwargs = _filter_kwargs(function, _strip_none(payload))
    return function(**kwargs)


def _call_verify_function(
    function: Any,
    capsule_path: Path,
    *,
    strict: bool,
    public_key_file: Path | None,
    require_signature_verifier: bool,
) -> Any:
    payload: dict[str, Any] = {
        "strict": strict,
        "public_key": _read_optional_bytes(public_key_file),
        "public_key_file": public_key_file,
        "public_key_path": public_key_file,
        "require_signature_verifier": require_signature_verifier,
    }

    try:
        kwargs = _filter_kwargs(function, _strip_none(payload))
        if kwargs:
            return function(capsule_path, **kwargs)
        return function(capsule_path)
    except Exception as exc:
        report = getattr(exc, "report", None)
        if report is not None:
            return report
        raise


def _filter_kwargs(function: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
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


def _normalize_build_result(request: BuildRequest, result: Any) -> BuildResult:
    if isinstance(result, BuildResult):
        return result

    data = _object_to_mapping(result)

    if data:
        return BuildResult(
            ok=bool(data.get("ok", True)),
            output=str(
                data.get("output")
                or data.get("capsule_file")
                or data.get("capsule_path")
                or request.output
            ),
            capsule_id=str(data.get("capsule_id", request.capsule_id)),
            capsule_version=str(data.get("capsule_version", request.capsule_version)),
            app_version=str(data.get("app_version", request.app_version)),
            param_version=str(data.get("param_version", request.param_version)),
            message=str(data.get("message", "Capsule build completed.")),
        )

    return BuildResult(
        ok=True,
        output=str(request.output),
        capsule_id=request.capsule_id,
        capsule_version=request.capsule_version,
        app_version=request.app_version,
        param_version=request.param_version,
        message="Capsule build completed.",
    )


def _normalize_verify_result(
    capsule_path: Path,
    result: Any,
    *,
    strict: bool = False,
) -> VerifyResult:
    if isinstance(result, VerifyResult):
        return result

    data = _object_to_mapping(result)

    errors = _issue_tuple(data.get("errors", ()))
    warnings = _issue_tuple(data.get("warnings", ()))
    checks = _issue_tuple(data.get("checks", ()))
    issues = _issue_tuple(data.get("issues", ()))

    if not issues:
        if errors:
            issues = errors
        elif checks:
            issues = checks
        elif warnings:
            issues = warnings

    ok = bool(
        data.get(
            "ok",
            data.get(
                "valid",
                data.get("passed", False),
            ),
        )
    )

    message = str(
        data.get(
            "message",
            "Capsule verification passed." if ok else "Capsule verification failed.",
        )
    )

    resolved_capsule_path = str(
        data.get("capsule_path")
        or data.get("capsule_file")
        or capsule_path
    )

    return VerifyResult(
        ok=ok,
        capsule_path=resolved_capsule_path,
        capsule_file=_optional_str(data.get("capsule_file") or resolved_capsule_path),
        message=message,
        issues=issues,
        errors=errors,
        warnings=warnings,
        checks=checks,
        capsule_id=_optional_str(data.get("capsule_id")),
        capsule_version=_optional_str(data.get("capsule_version")),
        app_version=_optional_str(data.get("app_version")),
        param_version=_optional_str(data.get("param_version")),
        manifest=_mapping_or_none(data.get("manifest")),
        strict=bool(data.get("strict", strict)),
    )


def _verify_result_from_validation_issues(
    capsule_path: Path,
    message: str,
    issues: Sequence[ValidationIssue],
    *,
    strict: bool,
) -> VerifyResult:
    issue_dicts = tuple(_validation_issue_to_dict(issue) for issue in issues)
    return VerifyResult(
        ok=False,
        capsule_path=str(capsule_path),
        capsule_file=str(capsule_path),
        message=message,
        issues=issue_dicts,
        errors=issue_dicts,
        checks=issue_dicts,
        strict=strict,
    )


def _object_to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, Mapping):
        return dict(value)

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        mapped = to_dict()
        if isinstance(mapped, Mapping):
            return dict(mapped)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        mapped = model_dump()
        if isinstance(mapped, Mapping):
            return dict(mapped)

    if is_dataclass(value):
        return asdict(value)

    data: dict[str, Any] = {}
    for key in (
        "ok",
        "valid",
        "passed",
        "capsule_path",
        "capsule_file",
        "capsule_id",
        "capsule_version",
        "app_version",
        "param_version",
        "message",
        "issues",
        "errors",
        "warnings",
        "checks",
        "manifest",
        "strict",
    ):
        if hasattr(value, key):
            data[key] = getattr(value, key)

    return data


def _issue_tuple(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value in (None, ""):
        return ()

    if isinstance(value, Mapping):
        return (_issue_to_dict(value),)

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_issue_to_dict(item) for item in value)

    return (_issue_to_dict(value),)


def _issue_to_dict(issue: Any) -> Mapping[str, Any]:
    if isinstance(issue, Mapping):
        return {str(key): _json_safe(value) for key, value in issue.items()}

    to_dict = getattr(issue, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, Mapping):
            return {str(key): _json_safe(item) for key, item in value.items()}

    model_dump = getattr(issue, "model_dump", None)
    if callable(model_dump):
        value = model_dump()
        if isinstance(value, Mapping):
            return {str(key): _json_safe(item) for key, item in value.items()}

    if is_dataclass(issue):
        return {str(key): _json_safe(value) for key, value in asdict(issue).items()}

    return {
        "code": _optional_str(getattr(issue, "code", None)) or "issue",
        "message": _optional_str(getattr(issue, "message", None)) or str(issue),
        "status": _enum_value(getattr(issue, "status", None)) or "",
        "path": _optional_str(getattr(issue, "path", None)),
    }


def _validation_issue_to_dict(issue: ValidationIssue) -> Mapping[str, Any]:
    return {
        "code": issue.code,
        "message": issue.message,
        "field": issue.field,
        "blocking": issue.blocking,
    }


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    if value in (None, ""):
        return None

    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if is_dataclass(value):
        return {str(key): _json_safe(item) for key, item in asdict(value).items()}

    return {"value": _json_safe(value)}


def _print_result(result: BuildResult | VerifyResult, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(_result_to_dict(result), indent=2, sort_keys=True, default=str))
        return

    if isinstance(result, BuildResult):
        status = "OK" if result.ok else "FAILED"
        print(f"{status}: {result.message or 'Capsule build finished.'}")
        print(f"output={result.output}")
        print(f"capsule_id={result.capsule_id}")
        print(f"capsule_version={result.capsule_version}")
        print(f"app_version={result.app_version}")
        print(f"param_version={result.param_version}")
        return

    status = "OK" if result.ok else "FAILED"
    print(f"{status}: {result.message or 'Capsule verification finished.'}")
    print(f"capsule={result.capsule_path}")

    if result.errors:
        print("errors:")
        for issue in result.errors:
            print(f"- {issue.get('code')}: {issue.get('message')}")

    if result.warnings:
        print("warnings:")
        for issue in result.warnings:
            print(f"- {issue.get('code')}: {issue.get('message')}")

    if result.issues and not result.errors:
        print("issues:")
        for issue in result.issues:
            print(f"- {issue.get('code')}: {issue.get('message')}")


def _print_error(
    message: str,
    *,
    issues: Sequence[ValidationIssue] = (),
    json_output: bool = False,
) -> None:
    if json_output:
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": message,
                    "issues": [_validation_issue_to_dict(issue) for issue in issues],
                },
                indent=2,
                sort_keys=True,
                default=str,
            ),
            file=sys.stderr,
        )
        return

    print(f"ERROR: {message}", file=sys.stderr)

    for issue in issues:
        print(f"- {issue.code}: {issue.message}", file=sys.stderr)


def _result_to_dict(result: BuildResult | VerifyResult) -> dict[str, Any]:
    return _json_safe(asdict(result))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    enum_value = _enum_value(value)
    if enum_value is not value:
        return enum_value

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


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(_enum_value(value))


def _strip_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _read_optional_bytes(path: Path | None) -> bytes | None:
    if path is None:
        return None
    return Path(path).read_bytes()


def _resolved_password(request: BuildRequest) -> str | None:
    if request.signing_key_password_file is not None:
        return request.signing_key_password_file.read_text(encoding="utf-8").strip()
    return request.signing_key_password


def _date_from_capsule_id(capsule_id: str) -> str:
    parts = capsule_id.rsplit("-", maxsplit=1)
    if len(parts) == 2 and parts[1]:
        return parts[1]
    return "2026.04.30"


# Compatibility alias for pyproject entrypoint:
# kx-builder = "kx_builder.main:app"
app = main


if __name__ == "__main__":
    main()
