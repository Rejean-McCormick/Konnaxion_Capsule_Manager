"""
Builder-side verification for Konnaxion Capsules.

This module verifies a built ``.kxcap`` before it is handed to the
Konnaxion Capsule Manager or imported by the Konnaxion Agent.

Scope:
- validate canonical capsule extension
- inspect required capsule root layout
- parse and validate manifest basics
- verify ``checksums.txt`` entries
- confirm ``signature.sig`` is present
- optionally call a caller-provided signature verifier
- reject obvious real secrets in env templates
- return a structured report suitable for CLI output and CI

This verifier does not start services, load OCI images, or mutate host state.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
import io
import json
import re
import tarfile
from typing import Any

try:  # pragma: no cover - optional dependency
    import yaml
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore[assignment]

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    CAPSULE_EXTENSION,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    NetworkProfile,
    PARAM_VERSION,
)


try:  # pragma: no cover - zstandard may not be installed in all dev envs
    import zstandard as zstd
except Exception:  # pragma: no cover
    zstd = None  # type: ignore[assignment]


SignatureVerifier = Callable[[bytes, bytes, bytes], bool]


class VerifyStatus(StrEnum):
    """Verification status values for builder checks."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class VerifyIssue:
    """Single verification issue."""

    code: str
    message: str
    status: VerifyStatus = VerifyStatus.FAIL
    path: str | None = None


@dataclass(frozen=True)
class CapsuleVerifyReport:
    """Structured verification report."""

    ok: bool
    capsule_path: Path
    capsule_id: str | None = None
    capsule_version: str | None = None
    app_version: str | None = None
    param_version: str | None = None
    checks: tuple[VerifyIssue, ...] = field(default_factory=tuple)
    warnings: tuple[VerifyIssue, ...] = field(default_factory=tuple)
    manifest: Mapping[str, Any] | None = None

    @property
    def errors(self) -> tuple[VerifyIssue, ...]:
        """Return blocking verification errors."""

        return tuple(issue for issue in self.checks if issue.status == VerifyStatus.FAIL)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report."""

        return {
            "ok": self.ok,
            "capsule_path": str(self.capsule_path),
            "capsule_id": self.capsule_id,
            "capsule_version": self.capsule_version,
            "app_version": self.app_version,
            "param_version": self.param_version,
            "errors": [issue_to_dict(issue) for issue in self.errors],
            "warnings": [issue_to_dict(issue) for issue in self.warnings],
            "checks": [issue_to_dict(issue) for issue in self.checks],
            "manifest": dict(self.manifest or {}),
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Return the report as JSON text."""

        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


class CapsuleVerifyError(ValueError):
    """Raised when caller requests exception-based verification."""

    def __init__(self, report: CapsuleVerifyReport) -> None:
        self.report = report
        detail = "; ".join(issue.message for issue in report.errors)
        super().__init__(detail or "Capsule verification failed")


@dataclass(frozen=True)
class CapsuleArchive:
    """In-memory representation of a capsule archive."""

    path: Path
    members: Mapping[str, bytes]

    def has(self, path: str) -> bool:
        """Return whether an archive member exists."""

        return path in self.members

    def read_text(self, path: str) -> str:
        """Read a member as UTF-8 text."""

        return self.members[path].decode("utf-8")

    def read_bytes(self, path: str) -> bytes:
        """Read a member as bytes."""

        return self.members[path]

    def list_paths(self) -> tuple[str, ...]:
        """Return all normalized member paths."""

        return tuple(sorted(self.members))


REQUIRED_ROOT_FILES = frozenset(
    {
        "manifest.yaml",
        "docker-compose.capsule.yml",
        "checksums.txt",
        "signature.sig",
    }
)

REQUIRED_ROOT_DIRS = frozenset(
    {
        "images",
        "profiles",
        "env-templates",
        "migrations",
        "healthchecks",
        "policies",
        "metadata",
    }
)

OPTIONAL_ROOT_DIRS = frozenset({"seed-data"})

REQUIRED_ENV_TEMPLATES = frozenset(
    {
        "env-templates/django.env.template",
        "env-templates/postgres.env.template",
        "env-templates/redis.env.template",
        "env-templates/frontend.env.template",
    }
)

REQUIRED_PROFILES = frozenset(
    {
        "profiles/local_only.yaml",
        "profiles/intranet_private.yaml",
        "profiles/private_tunnel.yaml",
        "profiles/public_temporary.yaml",
        "profiles/public_vps.yaml",
        "profiles/offline.yaml",
    }
)

SECRET_KEY_PATTERNS = (
    re.compile(r"^DJANGO_SECRET_KEY\s*=\s*(?!<GENERATED_ON_INSTALL>|\$\{)", re.I),
    re.compile(r"^POSTGRES_PASSWORD\s*=\s*(?!<GENERATED_ON_INSTALL>|\$\{)", re.I),
    re.compile(r"^DATABASE_URL\s*=\s*postgres://", re.I),
    re.compile(r"PRIVATE_KEY", re.I),
    re.compile(r"API_TOKEN\s*=\s*[^<\s]", re.I),
    re.compile(r"GIT_TOKEN\s*=\s*[^<\s]", re.I),
    re.compile(r"PROVIDER_TOKEN\s*=\s*[^<\s]", re.I),
)

CHECKSUM_LINE_RE = re.compile(r"^(?P<digest>[a-fA-F0-9]{64})\s+\*?(?P<path>.+)$")


def issue_to_dict(issue: VerifyIssue) -> dict[str, Any]:
    """Serialize a verification issue."""

    return {
        "code": issue.code,
        "message": issue.message,
        "status": issue.status.value,
        "path": issue.path,
    }


def verify_capsule(
    capsule_path: str | Path,
    *,
    public_key: bytes | None = None,
    signature_verifier: SignatureVerifier | None = None,
    require_signature_verifier: bool = False,
    raise_on_error: bool = False,
) -> CapsuleVerifyReport:
    """Verify a built Konnaxion Capsule.

    ``signature_verifier`` receives ``manifest_bytes``, ``checksums_bytes``,
    and ``signature_bytes`` and must return ``True`` when the signature is
    valid. Signature cryptography is deliberately injected so the project can
    choose minisign, age/signify, GPG, Sigstore, or another approved backend
    without changing the report contract.
    """

    path = Path(capsule_path)
    issues: list[VerifyIssue] = []
    warnings: list[VerifyIssue] = []
    manifest: Mapping[str, Any] | None = None

    def fail(code: str, message: str, member_path: str | None = None) -> None:
        issues.append(
            VerifyIssue(
                code=code,
                message=message,
                status=VerifyStatus.FAIL,
                path=member_path,
            )
        )

    def warn(code: str, message: str, member_path: str | None = None) -> None:
        issue = VerifyIssue(
            code=code,
            message=message,
            status=VerifyStatus.WARN,
            path=member_path,
        )
        warnings.append(issue)
        issues.append(issue)

    if not path.name.endswith(CAPSULE_EXTENSION):
        fail(
            "invalid_extension",
            f"Capsule must use canonical {CAPSULE_EXTENSION} extension",
            str(path),
        )

    if not path.exists():
        fail("missing_capsule", f"Capsule does not exist: {path}", str(path))
        report = _build_report(path, issues, warnings, manifest)
        if raise_on_error:
            raise CapsuleVerifyError(report)
        return report

    try:
        archive = read_capsule_archive(path)
    except Exception as exc:
        fail("unreadable_capsule", f"Could not read capsule archive: {exc}", str(path))
        report = _build_report(path, issues, warnings, manifest)
        if raise_on_error:
            raise CapsuleVerifyError(report)
        return report

    _verify_layout(archive, fail=fail, warn=warn)

    if archive.has("manifest.yaml"):
        try:
            manifest = parse_manifest(archive.read_bytes("manifest.yaml"))
            _verify_manifest(manifest, fail=fail, warn=warn)
        except Exception as exc:
            fail("invalid_manifest", f"Could not parse manifest.yaml: {exc}", "manifest.yaml")

    if archive.has("checksums.txt"):
        try:
            _verify_checksums(archive, fail=fail, warn=warn)
        except Exception as exc:
            fail("invalid_checksums", f"Could not verify checksums.txt: {exc}", "checksums.txt")

    _verify_signature(
        archive,
        public_key=public_key,
        signature_verifier=signature_verifier,
        require_signature_verifier=require_signature_verifier,
        fail=fail,
        warn=warn,
    )

    _verify_env_templates(archive, fail=fail, warn=warn)

    report = _build_report(path, issues, warnings, manifest)
    if raise_on_error and not report.ok:
        raise CapsuleVerifyError(report)
    return report


def assert_capsule_valid(capsule_path: str | Path, **kwargs: Any) -> CapsuleVerifyReport:
    """Verify a capsule and raise ``CapsuleVerifyError`` on failure."""

    return verify_capsule(capsule_path, raise_on_error=True, **kwargs)


def read_capsule_archive(path: str | Path) -> CapsuleArchive:
    """Read a ``.kxcap`` archive into memory.

    MVP capsules are expected to be tar archives with zstd compression. This
    reader also accepts regular tar files for local tests.
    """

    capsule_path = Path(path)
    raw = capsule_path.read_bytes()

    tar_bytes = raw
    if zstd is not None:
        try:
            tar_bytes = zstd.ZstdDecompressor().decompress(raw)
        except Exception:
            tar_bytes = raw

    members: dict[str, bytes] = {}

    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue

            normalized = normalize_archive_path(member.name)
            if normalized is None:
                raise CapsuleVerifyError(
                    CapsuleVerifyReport(
                        ok=False,
                        capsule_path=capsule_path,
                        checks=(
                            VerifyIssue(
                                code="unsafe_archive_path",
                                message=f"Unsafe archive path: {member.name}",
                                path=member.name,
                            ),
                        ),
                    )
                )

            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            members[normalized] = extracted.read()

    return CapsuleArchive(path=capsule_path, members=members)


def normalize_archive_path(path: str) -> str | None:
    """Normalize and validate a capsule archive member path."""

    pure = PurePosixPath(path)

    if pure.is_absolute():
        return None

    if ".." in pure.parts:
        return None

    normalized = str(pure)
    if normalized in {"", "."}:
        return None

    return normalized


def parse_manifest(content: bytes) -> Mapping[str, Any]:
    """Parse ``manifest.yaml``."""

    text = content.decode("utf-8")

    if yaml is not None:
        data = yaml.safe_load(text)
    else:
        # Minimal fallback for simple key: value manifests. This is not a full
        # YAML parser, but it keeps early CI smoke tests independent of PyYAML.
        data = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"').strip("'")

    if not isinstance(data, Mapping):
        raise ValueError("manifest.yaml must contain a mapping")

    return data


def _verify_layout(
    archive: CapsuleArchive,
    *,
    fail: Callable[[str, str, str | None], None],
    warn: Callable[[str, str, str | None], None],
) -> None:
    """Verify required capsule layout."""

    paths = set(archive.list_paths())

    for required_file in sorted(REQUIRED_ROOT_FILES):
        if required_file not in paths:
            fail(
                "missing_required_file",
                f"Capsule is missing required root file {required_file}",
                required_file,
            )

    for required_template in sorted(REQUIRED_ENV_TEMPLATES):
        if required_template not in paths:
            fail(
                "missing_env_template",
                f"Capsule is missing required env template {required_template}",
                required_template,
            )

    for required_profile in sorted(REQUIRED_PROFILES):
        if required_profile not in paths:
            fail(
                "missing_network_profile",
                f"Capsule is missing required network profile {required_profile}",
                required_profile,
            )

    root_entries = {path.split("/", 1)[0] for path in paths}
    for required_dir in sorted(REQUIRED_ROOT_DIRS):
        if required_dir not in root_entries:
            fail(
                "missing_required_directory",
                f"Capsule is missing required directory {required_dir}/",
                required_dir,
            )

    allowed_roots = REQUIRED_ROOT_FILES | REQUIRED_ROOT_DIRS | OPTIONAL_ROOT_DIRS
    for root in sorted(root_entries):
        if root not in allowed_roots:
            warn(
                "unknown_root_entry",
                f"Capsule contains non-canonical root entry {root}",
                root,
            )


def _verify_manifest(
    manifest: Mapping[str, Any],
    *,
    fail: Callable[[str, str, str | None], None],
    warn: Callable[[str, str, str | None], None],
) -> None:
    """Verify required manifest fields and canonical defaults."""

    required = {
        "schema_version",
        "capsule_id",
        "capsule_version",
        "app_name",
        "app_version",
        "channel",
        "created_at",
    }

    for key in sorted(required):
        if not manifest.get(key):
            fail("missing_manifest_field", f"manifest.yaml missing {key}", "manifest.yaml")

    app_name = str(manifest.get("app_name", ""))
    if app_name and app_name != "Konnaxion":
        fail(
            "invalid_app_name",
            "manifest.yaml app_name must be Konnaxion",
            "manifest.yaml",
        )

    app_version = str(manifest.get("app_version", ""))
    if app_version and app_version != APP_VERSION:
        fail(
            "invalid_app_version",
            f"manifest.yaml app_version must be {APP_VERSION}",
            "manifest.yaml",
        )

    capsule_id = str(manifest.get("capsule_id", ""))
    if capsule_id and not capsule_id.startswith("konnaxion-v14-"):
        fail(
            "invalid_capsule_id",
            "manifest.yaml capsule_id must start with konnaxion-v14-",
            "manifest.yaml",
        )

    capsule_version = str(manifest.get("capsule_version", ""))
    if capsule_version and capsule_version == DEFAULT_CAPSULE_VERSION:
        warn(
            "default_capsule_version",
            "manifest.yaml uses the default demo capsule version",
            "manifest.yaml",
        )

    if capsule_id == DEFAULT_CAPSULE_ID:
        warn(
            "default_capsule_id",
            "manifest.yaml uses the default demo capsule id",
            "manifest.yaml",
        )

    param_version = str(manifest.get("param_version", ""))
    if param_version and param_version != PARAM_VERSION:
        warn(
            "param_version_mismatch",
            f"manifest.yaml param_version differs from canonical {PARAM_VERSION}",
            "manifest.yaml",
        )

    profiles = manifest.get("profiles")
    if profiles is not None:
        profile_values = set()
        if isinstance(profiles, Mapping):
            profile_values = {str(key) for key in profiles.keys()}
        elif isinstance(profiles, Iterable) and not isinstance(profiles, (str, bytes)):
            profile_values = {str(item) for item in profiles}

        allowed_profiles = {profile.value for profile in NetworkProfile}
        unknown = sorted(profile_values - allowed_profiles)
        if unknown:
            fail(
                "invalid_manifest_profiles",
                f"manifest.yaml contains non-canonical profiles: {', '.join(unknown)}",
                "manifest.yaml",
            )


def _verify_checksums(
    archive: CapsuleArchive,
    *,
    fail: Callable[[str, str, str | None], None],
    warn: Callable[[str, str, str | None], None],
) -> None:
    """Verify ``checksums.txt`` entries against archive contents."""

    text = archive.read_text("checksums.txt")
    seen: set[str] = set()

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = CHECKSUM_LINE_RE.match(line)
        if not match:
            fail(
                "invalid_checksum_line",
                f"Invalid checksums.txt line {line_number}",
                "checksums.txt",
            )
            continue

        digest = match.group("digest").lower()
        member_path = normalize_archive_path(match.group("path").strip())

        if member_path is None:
            fail(
                "unsafe_checksum_path",
                f"Unsafe checksums.txt path on line {line_number}",
                "checksums.txt",
            )
            continue

        if member_path == "checksums.txt":
            warn(
                "checksum_self_reference",
                "checksums.txt should not checksum itself",
                "checksums.txt",
            )
            continue

        if not archive.has(member_path):
            fail(
                "checksum_missing_member",
                f"checksums.txt references missing member {member_path}",
                member_path,
            )
            continue

        actual = sha256(archive.read_bytes(member_path)).hexdigest()
        if actual != digest:
            fail(
                "checksum_mismatch",
                f"Checksum mismatch for {member_path}",
                member_path,
            )

        seen.add(member_path)

    for required in sorted(REQUIRED_ROOT_FILES - {"checksums.txt", "signature.sig"}):
        if archive.has(required) and required not in seen:
            warn(
                "required_file_not_checksummed",
                f"{required} is not listed in checksums.txt",
                required,
            )


def _verify_signature(
    archive: CapsuleArchive,
    *,
    public_key: bytes | None,
    signature_verifier: SignatureVerifier | None,
    require_signature_verifier: bool,
    fail: Callable[[str, str, str | None], None],
    warn: Callable[[str, str, str | None], None],
) -> None:
    """Verify signature presence and optionally cryptographic validity."""

    if not archive.has("signature.sig"):
        fail(
            "missing_signature",
            "Capsule is missing mandatory signature.sig",
            "signature.sig",
        )
        return

    if not archive.has("manifest.yaml") or not archive.has("checksums.txt"):
        fail(
            "signature_inputs_missing",
            "Cannot verify signature without manifest.yaml and checksums.txt",
            "signature.sig",
        )
        return

    if signature_verifier is None:
        if require_signature_verifier:
            fail(
                "signature_verifier_missing",
                "A signature verifier is required but was not provided",
                "signature.sig",
            )
        else:
            warn(
                "signature_not_cryptographically_verified",
                "signature.sig is present but no cryptographic verifier was provided",
                "signature.sig",
            )
        return

    if public_key is None:
        fail(
            "public_key_missing",
            "A public key is required for cryptographic signature verification",
            "signature.sig",
        )
        return

    ok = signature_verifier(
        archive.read_bytes("manifest.yaml"),
        archive.read_bytes("checksums.txt"),
        archive.read_bytes("signature.sig"),
    )

    if not ok:
        fail(
            "signature_invalid",
            "Capsule signature verification failed",
            "signature.sig",
        )


def _verify_env_templates(
    archive: CapsuleArchive,
    *,
    fail: Callable[[str, str, str | None], None],
    warn: Callable[[str, str, str | None], None],
) -> None:
    """Reject obvious real secrets in env templates."""

    for path in archive.list_paths():
        if not path.startswith("env-templates/"):
            continue

        if not path.endswith((".template", ".env", ".txt")):
            continue

        text = archive.read_text(path)
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            for pattern in SECRET_KEY_PATTERNS:
                if pattern.search(stripped):
                    fail(
                        "possible_real_secret",
                        f"Possible real secret in {path} line {line_number}",
                        path,
                    )

        if "DJANGO_SECRET_KEY=<GENERATED_ON_INSTALL>" not in text and path.endswith(
            "django.env.template"
        ):
            warn(
                "missing_django_secret_placeholder",
                "django.env.template should include DJANGO_SECRET_KEY=<GENERATED_ON_INSTALL>",
                path,
            )

        if "POSTGRES_PASSWORD=<GENERATED_ON_INSTALL>" not in text and path.endswith(
            "postgres.env.template"
        ):
            warn(
                "missing_postgres_password_placeholder",
                "postgres.env.template should include POSTGRES_PASSWORD=<GENERATED_ON_INSTALL>",
                path,
            )


def _build_report(
    path: Path,
    issues: Iterable[VerifyIssue],
    warnings: Iterable[VerifyIssue],
    manifest: Mapping[str, Any] | None,
) -> CapsuleVerifyReport:
    """Build final report from accumulated issues."""

    issue_tuple = tuple(issues)
    manifest_data = dict(manifest or {})

    return CapsuleVerifyReport(
        ok=not any(issue.status == VerifyStatus.FAIL for issue in issue_tuple),
        capsule_path=path,
        capsule_id=_optional_str(manifest_data.get("capsule_id")),
        capsule_version=_optional_str(manifest_data.get("capsule_version")),
        app_version=_optional_str(manifest_data.get("app_version")),
        param_version=_optional_str(manifest_data.get("param_version")),
        checks=issue_tuple,
        warnings=tuple(warnings),
        manifest=manifest_data if manifest_data else None,
    )


def _optional_str(value: Any) -> str | None:
    """Return optional value as string."""

    if value in {None, ""}:
        return None
    return str(value)


__all__ = [
    "CapsuleArchive",
    "CapsuleVerifyError",
    "CapsuleVerifyReport",
    "SignatureVerifier",
    "VerifyIssue",
    "VerifyStatus",
    "assert_capsule_valid",
    "issue_to_dict",
    "normalize_archive_path",
    "parse_manifest",
    "read_capsule_archive",
    "verify_capsule",
]
