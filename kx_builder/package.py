"""
Konnaxion Capsule packaging utilities.

A Konnaxion Capsule is the signed, portable deployment artifact consumed by the
Konnaxion Capsule Manager and Agent.

Canonical user-facing extension:

    .kxcap

MVP physical format:

    tar archive + zstd compression

This module is responsible for packaging an already-prepared capsule staging
directory. It does not build Docker images, generate the manifest, or sign the
capsule; those steps belong to builder modules such as images.py, manifest.py,
checksums.py, and signature.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    CAPSULE_EXTENSION,
    CAPSULE_FILENAME_PATTERN,
    DEFAULT_CHANNEL,
    KX_CAPSULES_DIR,
)


PACKAGE_SCHEMA_VERSION = "kx-package/v1"

MANIFEST_FILENAME = "manifest.yaml"
COMPOSE_FILENAME = "docker-compose.capsule.yml"
CHECKSUMS_FILENAME = "checksums.txt"
SIGNATURE_FILENAME = "signature.sig"

REQUIRED_ROOT_FILES = frozenset(
    {
        MANIFEST_FILENAME,
        COMPOSE_FILENAME,
        CHECKSUMS_FILENAME,
        SIGNATURE_FILENAME,
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

OPTIONAL_ROOT_DIRS = frozenset(
    {
        "seed-data",
    }
)

ALLOWED_ROOT_ENTRIES = REQUIRED_ROOT_FILES | REQUIRED_ROOT_DIRS | OPTIONAL_ROOT_DIRS

FORBIDDEN_CAPSULE_FILENAMES = frozenset(
    {
        ".env",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "authorized_keys",
        "known_hosts",
        "docker.sock",
        "kubeconfig",
        "credentials",
        "credentials.json",
        "service-account.json",
    }
)

FORBIDDEN_FILENAME_PATTERNS = (
    re.compile(r".*\.pem$", re.IGNORECASE),
    re.compile(r".*\.key$", re.IGNORECASE),
    re.compile(r".*private.*key.*", re.IGNORECASE),
    re.compile(r".*secret.*", re.IGNORECASE),
    re.compile(r".*token.*", re.IGNORECASE),
    re.compile(r".*password.*", re.IGNORECASE),
)

FORBIDDEN_TEXT_PATTERNS = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"DJANGO_SECRET_KEY\s*=\s*['\"]?[^<'\"\s][^'\"\n]*"),
    re.compile(rb"POSTGRES_PASSWORD\s*=\s*['\"]?[^<'\"\s][^'\"\n]*"),
    re.compile(rb"DATABASE_URL\s*=\s*postgres://[^<\s]+"),
    re.compile(rb"REDIS_URL\s*=\s*redis://[^<\s]+"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"ghp_[A-Za-z0-9_]{20,}"),
)

TEXT_SCAN_EXTENSIONS = frozenset(
    {
        ".env",
        ".template",
        ".txt",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".md",
    }
)

DEFAULT_COMPRESSION_LEVEL = 19
DEFAULT_COMMAND_TIMEOUT_SECONDS = 300


class PackageCompression(StrEnum):
    """Supported capsule compression modes."""

    ZSTD = "zstd"


class PackageIssueSeverity(StrEnum):
    """Packaging validation issue severity."""

    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class PackageIssue:
    """One package validation issue."""

    severity: PackageIssueSeverity
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class PackageValidationResult:
    """Validation result for a capsule staging directory or artifact."""

    ok: bool
    issues: tuple[PackageIssue, ...] = ()

    @property
    def blocking_issues(self) -> tuple[PackageIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == PackageIssueSeverity.BLOCKING)

    @property
    def warnings(self) -> tuple[PackageIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == PackageIssueSeverity.WARNING)


@dataclass(frozen=True, slots=True)
class PackageOptions:
    """Options used when creating a .kxcap artifact."""

    compression: PackageCompression = PackageCompression.ZSTD
    compression_level: int = DEFAULT_COMPRESSION_LEVEL
    deterministic: bool = True
    strict_root: bool = True
    scan_for_secrets: bool = True
    overwrite: bool = False
    include_package_metadata: bool = True


@dataclass(frozen=True, slots=True)
class PackageResult:
    """Result returned after creating a capsule artifact."""

    capsule_file: Path
    staging_dir: Path
    size_bytes: int
    sha256: str
    created_at: datetime
    compression: PackageCompression
    metadata_file: Path | None = None


@dataclass(frozen=True, slots=True)
class CapsuleArchiveEntry:
    """One file entry discovered inside a .kxcap archive."""

    path: str
    size: int
    mode: int
    type: str


@dataclass(frozen=True, slots=True)
class CapsuleArchiveInfo:
    """Summary of a packaged .kxcap file."""

    capsule_file: Path
    size_bytes: int
    sha256: str
    entries: tuple[CapsuleArchiveEntry, ...]


class PackageError(RuntimeError):
    """Base packaging error."""


class PackageValidationError(PackageError):
    """Raised when a capsule staging directory is invalid."""

    def __init__(self, result: PackageValidationResult) -> None:
        self.result = result
        messages = "; ".join(issue.message for issue in result.blocking_issues)
        super().__init__(messages or "capsule validation failed")


class CompressionUnavailableError(PackageError):
    """Raised when no zstd compressor/decompressor is available."""


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""

    return datetime.now(UTC)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def ensure_capsule_extension(path: Path | str) -> Path:
    """Return path with canonical .kxcap extension enforced."""

    output = Path(path)
    if output.suffix != CAPSULE_EXTENSION:
        raise ValueError(f"capsule output must end with {CAPSULE_EXTENSION}: {output}")
    return output


def capsule_filename(
    *,
    channel: str = DEFAULT_CHANNEL,
    date: datetime | None = None,
) -> str:
    """Create a canonical capsule filename from the shared filename pattern."""

    timestamp = date or utc_now()
    return CAPSULE_FILENAME_PATTERN.format(
        channel=channel,
        date=timestamp.strftime("%Y.%m.%d"),
    )


def default_output_path(
    *,
    channel: str = DEFAULT_CHANNEL,
    output_dir: Path | str = KX_CAPSULES_DIR,
    date: datetime | None = None,
) -> Path:
    """Build the default output path for a packaged capsule."""

    return Path(output_dir) / capsule_filename(channel=channel, date=date)


def sha256_file(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a file SHA-256 digest."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(path: Path, root: Path) -> str:
    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise PackageError(f"path escapes staging root: {path}") from exc

    relative_text = relative.as_posix()
    if relative_text == "." or relative_text.startswith("../") or relative_text.startswith("/"):
        raise PackageError(f"unsafe relative path: {relative_text}")
    return relative_text


def iter_staging_files(staging_dir: Path | str) -> tuple[Path, ...]:
    """Return deterministic file list under a staging directory."""

    root = Path(staging_dir)
    files = [path for path in root.rglob("*") if path.is_file() or path.is_symlink()]
    return tuple(sorted(files, key=lambda item: _safe_relative_path(item, root)))


def root_entries(staging_dir: Path | str) -> set[str]:
    """Return root entry names from a staging directory."""

    root = Path(staging_dir)
    if not root.exists():
        return set()
    return {path.name for path in root.iterdir()}


def validate_required_layout(
    staging_dir: Path | str,
    *,
    strict_root: bool = True,
) -> list[PackageIssue]:
    """Validate the canonical .kxcap root layout."""

    root = Path(staging_dir)
    issues: list[PackageIssue] = []

    if not root.exists():
        return [
            PackageIssue(
                PackageIssueSeverity.BLOCKING,
                str(root),
                "capsule staging directory does not exist",
            )
        ]

    if not root.is_dir():
        return [
            PackageIssue(
                PackageIssueSeverity.BLOCKING,
                str(root),
                "capsule staging path is not a directory",
            )
        ]

    for filename in sorted(REQUIRED_ROOT_FILES):
        path = root / filename
        if not path.is_file():
            issues.append(
                PackageIssue(
                    PackageIssueSeverity.BLOCKING,
                    filename,
                    f"required capsule file is missing: {filename}",
                )
            )

    for dirname in sorted(REQUIRED_ROOT_DIRS):
        path = root / dirname
        if not path.is_dir():
            issues.append(
                PackageIssue(
                    PackageIssueSeverity.BLOCKING,
                    dirname,
                    f"required capsule directory is missing: {dirname}",
                )
            )

    if strict_root:
        extra = sorted(root_entries(root) - ALLOWED_ROOT_ENTRIES)
        for entry in extra:
            issues.append(
                PackageIssue(
                    PackageIssueSeverity.WARNING,
                    entry,
                    f"non-canonical root entry will be packaged: {entry}",
                )
            )

    return issues


def _filename_is_forbidden(path: Path) -> bool:
    name = path.name
    if name in FORBIDDEN_CAPSULE_FILENAMES:
        return True
    return any(pattern.fullmatch(name) for pattern in FORBIDDEN_FILENAME_PATTERNS)


def _should_scan_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SCAN_EXTENSIONS or path.name in FORBIDDEN_CAPSULE_FILENAMES


def scan_file_for_secret_patterns(path: Path, root: Path) -> list[PackageIssue]:
    """Scan one file for obvious secret patterns."""

    issues: list[PackageIssue] = []
    relative = _safe_relative_path(path, root)

    if _filename_is_forbidden(path):
        issues.append(
            PackageIssue(
                PackageIssueSeverity.BLOCKING,
                relative,
                f"forbidden secret-like filename in capsule: {relative}",
            )
        )

    if not _should_scan_text(path):
        return issues

    try:
        data = path.read_bytes()
    except OSError as exc:
        issues.append(
            PackageIssue(
                PackageIssueSeverity.BLOCKING,
                relative,
                f"could not read file for secret scan: {exc}",
            )
        )
        return issues

    for pattern in FORBIDDEN_TEXT_PATTERNS:
        if pattern.search(data):
            issues.append(
                PackageIssue(
                    PackageIssueSeverity.BLOCKING,
                    relative,
                    f"secret-like content detected in capsule file: {relative}",
                )
            )
            break

    return issues


def scan_staging_for_secrets(staging_dir: Path | str) -> list[PackageIssue]:
    """Scan staging files for obvious secrets that must not enter a capsule."""

    root = Path(staging_dir)
    issues: list[PackageIssue] = []

    for path in iter_staging_files(root):
        if path.is_symlink():
            issues.append(
                PackageIssue(
                    PackageIssueSeverity.BLOCKING,
                    _safe_relative_path(path, root),
                    "symlinks are not allowed in capsule staging",
                )
            )
            continue
        issues.extend(scan_file_for_secret_patterns(path, root))

    return issues


def validate_staging_dir(
    staging_dir: Path | str,
    *,
    options: PackageOptions | None = None,
) -> PackageValidationResult:
    """Validate a capsule staging directory."""

    resolved_options = options or PackageOptions()
    issues: list[PackageIssue] = []

    issues.extend(
        validate_required_layout(
            staging_dir,
            strict_root=resolved_options.strict_root,
        )
    )

    if resolved_options.scan_for_secrets:
        issues.extend(scan_staging_for_secrets(staging_dir))

    blocking = [issue for issue in issues if issue.severity == PackageIssueSeverity.BLOCKING]
    return PackageValidationResult(ok=not blocking, issues=tuple(issues))


def raise_if_invalid(result: PackageValidationResult) -> None:
    """Raise PackageValidationError if validation failed."""

    if not result.ok:
        raise PackageValidationError(result)


def _deterministic_tarinfo(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
    tarinfo.uid = 0
    tarinfo.gid = 0
    tarinfo.uname = "root"
    tarinfo.gname = "root"
    tarinfo.mtime = 0
    if tarinfo.isfile():
        tarinfo.mode = 0o644
    elif tarinfo.isdir():
        tarinfo.mode = 0o755
    return tarinfo


def create_tar_archive(
    staging_dir: Path | str,
    tar_path: Path | str,
    *,
    deterministic: bool = True,
) -> Path:
    """Create an intermediate tar archive from staging contents."""

    root = Path(staging_dir)
    output = Path(tar_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    filter_func = _deterministic_tarinfo if deterministic else None

    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as tar:
        # Add directories first for stable extraction behavior.
        dirs = sorted(
            [path for path in root.rglob("*") if path.is_dir()],
            key=lambda item: _safe_relative_path(item, root),
        )
        for directory in dirs:
            arcname = _safe_relative_path(directory, root)
            tar.add(directory, arcname=arcname, recursive=False, filter=filter_func)

        for file_path in iter_staging_files(root):
            arcname = _safe_relative_path(file_path, root)
            tar.add(file_path, arcname=arcname, recursive=False, filter=filter_func)

    return output


def _compress_with_python_zstandard(
    tar_path: Path,
    output_path: Path,
    *,
    level: int,
) -> bool:
    """Compress using optional zstandard Python package if installed."""

    try:
        import zstandard as zstd  # type: ignore[import-not-found]
    except ImportError:
        return False

    compressor = zstd.ZstdCompressor(level=level)
    with tar_path.open("rb") as source, output_path.open("wb") as target:
        compressor.copy_stream(source, target)
    return True


def _decompress_with_python_zstandard(
    capsule_path: Path,
    tar_path: Path,
) -> bool:
    """Decompress using optional zstandard Python package if installed."""

    try:
        import zstandard as zstd  # type: ignore[import-not-found]
    except ImportError:
        return False

    decompressor = zstd.ZstdDecompressor()
    with capsule_path.open("rb") as source, tar_path.open("wb") as target:
        decompressor.copy_stream(source, target)
    return True


def _zstd_binary() -> str | None:
    return shutil.which("zstd")


def _compress_with_zstd_binary(
    tar_path: Path,
    output_path: Path,
    *,
    level: int,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> bool:
    """Compress using zstd CLI if installed."""

    zstd_bin = _zstd_binary()
    if not zstd_bin:
        return False

    subprocess.run(
        [
            zstd_bin,
            f"-{level}",
            "--force",
            "--quiet",
            "-o",
            str(output_path),
            str(tar_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return True


def _decompress_with_zstd_binary(
    capsule_path: Path,
    tar_path: Path,
    *,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> bool:
    """Decompress using zstd CLI if installed."""

    zstd_bin = _zstd_binary()
    if not zstd_bin:
        return False

    subprocess.run(
        [
            zstd_bin,
            "--decompress",
            "--force",
            "--quiet",
            "-o",
            str(tar_path),
            str(capsule_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return True


def compress_tar_to_kxcap(
    tar_path: Path | str,
    output_path: Path | str,
    *,
    level: int = DEFAULT_COMPRESSION_LEVEL,
) -> Path:
    """Compress a tar archive to a .kxcap zstd artifact."""

    source = Path(tar_path)
    output = ensure_capsule_extension(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.exists():
        output.unlink()

    if _compress_with_python_zstandard(source, output, level=level):
        return output

    if _compress_with_zstd_binary(source, output, level=level):
        return output

    raise CompressionUnavailableError(
        "zstd compression unavailable: install python package 'zstandard' or the 'zstd' CLI"
    )


def decompress_kxcap_to_tar(
    capsule_file: Path | str,
    tar_path: Path | str,
) -> Path:
    """Decompress a .kxcap artifact to a temporary tar archive."""

    source = ensure_capsule_extension(capsule_file)
    output = Path(tar_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if _decompress_with_python_zstandard(source, output):
        return output

    if _decompress_with_zstd_binary(source, output):
        return output

    raise CompressionUnavailableError(
        "zstd decompression unavailable: install python package 'zstandard' or the 'zstd' CLI"
    )


def write_package_metadata(
    staging_dir: Path | str,
    *,
    package_result: Mapping[str, Any] | None = None,
) -> Path:
    """Write package metadata under metadata/package.json."""

    root = Path(staging_dir)
    metadata_dir = root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = metadata_dir / "package.json"

    payload = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "created_at": utc_now(),
        "format": "tar+zstd",
        "extension": CAPSULE_EXTENSION,
        "package_result": dict(package_result or {}),
    }
    metadata_file.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    return metadata_file


def package_capsule(
    staging_dir: Path | str,
    output_path: Path | str,
    *,
    options: PackageOptions | None = None,
) -> PackageResult:
    """Validate and package a capsule staging directory into a .kxcap file."""

    resolved_options = options or PackageOptions()
    root = Path(staging_dir)
    output = ensure_capsule_extension(output_path)

    validation = validate_staging_dir(root, options=resolved_options)
    raise_if_invalid(validation)

    if output.exists() and not resolved_options.overwrite:
        raise FileExistsError(f"capsule output already exists: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)

    metadata_file: Path | None = None
    if resolved_options.include_package_metadata:
        metadata_file = write_package_metadata(
            root,
            package_result={
                "output_path": str(output),
                "compression": resolved_options.compression.value,
            },
        )

    with tempfile.TemporaryDirectory(prefix="kxcap-package-") as tmp_dir:
        tar_path = Path(tmp_dir) / "capsule.tar"
        create_tar_archive(
            root,
            tar_path,
            deterministic=resolved_options.deterministic,
        )

        if resolved_options.compression != PackageCompression.ZSTD:
            raise PackageError(f"unsupported compression: {resolved_options.compression}")

        if output.exists():
            output.unlink()

        compress_tar_to_kxcap(
            tar_path,
            output,
            level=resolved_options.compression_level,
        )

    return PackageResult(
        capsule_file=output,
        staging_dir=root,
        size_bytes=output.stat().st_size,
        sha256=sha256_file(output),
        created_at=utc_now(),
        compression=resolved_options.compression,
        metadata_file=metadata_file,
    )


def package_to_default_location(
    staging_dir: Path | str,
    *,
    channel: str = DEFAULT_CHANNEL,
    output_dir: Path | str = KX_CAPSULES_DIR,
    options: PackageOptions | None = None,
    date: datetime | None = None,
) -> PackageResult:
    """Package a capsule to the canonical output directory and filename."""

    output = default_output_path(channel=channel, output_dir=output_dir, date=date)
    return package_capsule(staging_dir, output, options=options)


def read_tar_entries(tar_path: Path | str) -> tuple[CapsuleArchiveEntry, ...]:
    """Read archive entries from an uncompressed tar archive."""

    entries: list[CapsuleArchiveEntry] = []
    with tarfile.open(tar_path, "r") as tar:
        for member in tar.getmembers():
            if member.isdir():
                entry_type = "directory"
            elif member.isfile():
                entry_type = "file"
            elif member.issym():
                entry_type = "symlink"
            else:
                entry_type = "other"

            entries.append(
                CapsuleArchiveEntry(
                    path=member.name,
                    size=member.size,
                    mode=member.mode,
                    type=entry_type,
                )
            )

    return tuple(entries)


def inspect_capsule(capsule_file: Path | str) -> CapsuleArchiveInfo:
    """Inspect a .kxcap file without extracting it to a final destination."""

    source = ensure_capsule_extension(capsule_file)

    with tempfile.TemporaryDirectory(prefix="kxcap-inspect-") as tmp_dir:
        tar_path = Path(tmp_dir) / "capsule.tar"
        decompress_kxcap_to_tar(source, tar_path)
        entries = read_tar_entries(tar_path)

    return CapsuleArchiveInfo(
        capsule_file=source,
        size_bytes=source.stat().st_size,
        sha256=sha256_file(source),
        entries=entries,
    )


def validate_capsule_archive(capsule_file: Path | str) -> PackageValidationResult:
    """Validate a packaged .kxcap archive root layout."""

    source = ensure_capsule_extension(capsule_file)
    issues: list[PackageIssue] = []

    if not source.exists():
        return PackageValidationResult(
            ok=False,
            issues=(
                PackageIssue(
                    PackageIssueSeverity.BLOCKING,
                    str(source),
                    "capsule file does not exist",
                ),
            ),
        )

    try:
        info = inspect_capsule(source)
    except Exception as exc:
        return PackageValidationResult(
            ok=False,
            issues=(
                PackageIssue(
                    PackageIssueSeverity.BLOCKING,
                    str(source),
                    f"could not inspect capsule archive: {exc}",
                ),
            ),
        )

    entry_names = {entry.path.split("/", 1)[0] for entry in info.entries}

    for required_file in sorted(REQUIRED_ROOT_FILES):
        if required_file not in {entry.path for entry in info.entries if entry.type == "file"}:
            issues.append(
                PackageIssue(
                    PackageIssueSeverity.BLOCKING,
                    required_file,
                    f"required capsule file is missing from archive: {required_file}",
                )
            )

    for required_dir in sorted(REQUIRED_ROOT_DIRS):
        if required_dir not in entry_names:
            issues.append(
                PackageIssue(
                    PackageIssueSeverity.BLOCKING,
                    required_dir,
                    f"required capsule directory is missing from archive: {required_dir}",
                )
            )

    for entry in info.entries:
        path = Path(entry.path)
        if path.name in FORBIDDEN_CAPSULE_FILENAMES:
            issues.append(
                PackageIssue(
                    PackageIssueSeverity.BLOCKING,
                    entry.path,
                    f"forbidden filename present in archive: {entry.path}",
                )
            )
        if entry.type == "symlink":
            issues.append(
                PackageIssue(
                    PackageIssueSeverity.BLOCKING,
                    entry.path,
                    "symlink present in archive",
                )
            )

    blocking = [issue for issue in issues if issue.severity == PackageIssueSeverity.BLOCKING]
    return PackageValidationResult(ok=not blocking, issues=tuple(issues))


def extract_capsule(
    capsule_file: Path | str,
    destination_dir: Path | str,
    *,
    overwrite: bool = False,
) -> Path:
    """Extract a .kxcap archive to a destination directory safely.

    This helper is mainly for tests and inspection. Runtime import should be
    owned by kx_agent.capsules.importer.
    """

    source = ensure_capsule_extension(capsule_file)
    destination = Path(destination_dir)

    if destination.exists() and any(destination.iterdir()) and not overwrite:
        raise FileExistsError(f"destination is not empty: {destination}")

    destination.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="kxcap-extract-") as tmp_dir:
        tar_path = Path(tmp_dir) / "capsule.tar"
        decompress_kxcap_to_tar(source, tar_path)

        with tarfile.open(tar_path, "r") as tar:
            for member in tar.getmembers():
                target = (destination / member.name).resolve(strict=False)
                try:
                    target.relative_to(destination.resolve(strict=False))
                except ValueError as exc:
                    raise PackageError(f"archive member escapes destination: {member.name}") from exc
                if member.issym() or member.islnk():
                    raise PackageError(f"archive member is a link and is not allowed: {member.name}")
            tar.extractall(destination)

    return destination


def package_result_to_dict(result: PackageResult) -> dict[str, Any]:
    """Serialize a package result."""

    return json.loads(json.dumps(asdict(result), default=_json_default))


def validation_result_to_dict(result: PackageValidationResult) -> dict[str, Any]:
    """Serialize a validation result."""

    return json.loads(json.dumps(asdict(result), default=_json_default))


__all__ = [
    "ALLOWED_ROOT_ENTRIES",
    "CHECKSUMS_FILENAME",
    "COMPOSE_FILENAME",
    "DEFAULT_COMMAND_TIMEOUT_SECONDS",
    "DEFAULT_COMPRESSION_LEVEL",
    "FORBIDDEN_CAPSULE_FILENAMES",
    "FORBIDDEN_FILENAME_PATTERNS",
    "FORBIDDEN_TEXT_PATTERNS",
    "MANIFEST_FILENAME",
    "OPTIONAL_ROOT_DIRS",
    "PACKAGE_SCHEMA_VERSION",
    "REQUIRED_ROOT_DIRS",
    "REQUIRED_ROOT_FILES",
    "SIGNATURE_FILENAME",
    "TEXT_SCAN_EXTENSIONS",
    "CapsuleArchiveEntry",
    "CapsuleArchiveInfo",
    "CompressionUnavailableError",
    "PackageCompression",
    "PackageError",
    "PackageIssue",
    "PackageIssueSeverity",
    "PackageOptions",
    "PackageResult",
    "PackageValidationError",
    "PackageValidationResult",
    "capsule_filename",
    "compress_tar_to_kxcap",
    "create_tar_archive",
    "decompress_kxcap_to_tar",
    "default_output_path",
    "ensure_capsule_extension",
    "extract_capsule",
    "inspect_capsule",
    "iter_staging_files",
    "package_capsule",
    "package_result_to_dict",
    "package_to_default_location",
    "raise_if_invalid",
    "read_tar_entries",
    "root_entries",
    "scan_file_for_secret_patterns",
    "scan_staging_for_secrets",
    "sha256_file",
    "utc_now",
    "validate_capsule_archive",
    "validate_required_layout",
    "validate_staging_dir",
    "validation_result_to_dict",
    "write_package_metadata",
]
