"""
Source tree inspection for Konnaxion Capsule Builder.

The Builder uses this module before creating a `.kxcap` to verify that the
source repository contains the expected Konnaxion application structure and does
not include secret-bearing files in capsule inputs.

This module does not build Docker images, sign capsules, or write runtime
configuration. It only inspects and classifies files so later Builder stages can
make deterministic decisions.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    BUILDER_NAME,
    CAPSULE_EXTENSION,
    DockerService,
    PARAM_VERSION,
)


class SourceTreeError(ValueError):
    """Raised when a source tree cannot be used to build a capsule."""


class SourceTreeSeverity(StrEnum):
    """Validation issue severity."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SourceTreeArea(StrEnum):
    """Logical area of the Konnaxion source tree."""

    ROOT = "root"
    FRONTEND = "frontend"
    BACKEND = "backend"
    DOCKER = "docker"
    DOCS = "docs"
    CONFIG = "config"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceTreeIssue:
    """One validation finding."""

    severity: SourceTreeSeverity
    code: str
    message: str
    path: str = ""
    area: SourceTreeArea = SourceTreeArea.UNKNOWN

    def to_dict(self) -> dict[str, str]:
        data = asdict(self)
        data["severity"] = self.severity.value
        data["area"] = self.area.value
        return data


@dataclass(frozen=True)
class SourceFile:
    """A file discovered in the source tree."""

    path: str
    area: SourceTreeArea
    size_bytes: int
    sha256: str
    capsule_input: bool = True

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["area"] = self.area.value
        return data


@dataclass(frozen=True)
class SourceTreeReport:
    """Validation and inventory report for a source tree."""

    root: str
    app_version: str
    param_version: str
    files: tuple[SourceFile, ...]
    issues: tuple[SourceTreeIssue, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(issue.severity == SourceTreeSeverity.ERROR for issue in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == SourceTreeSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == SourceTreeSeverity.WARNING)

    @property
    def capsule_inputs(self) -> tuple[SourceFile, ...]:
        return tuple(file for file in self.files if file.capsule_input)

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "app_version": self.app_version,
            "param_version": self.param_version,
            "ok": self.ok,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "files": [file.to_dict() for file in self.files],
            "issues": [issue.to_dict() for issue in self.issues],
            "metadata": dict(self.metadata),
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def raise_for_errors(self) -> None:
        if self.ok:
            return

        messages = [
            f"{issue.code}: {issue.message}"
            + (f" ({issue.path})" if issue.path else "")
            for issue in self.issues
            if issue.severity == SourceTreeSeverity.ERROR
        ]

        raise SourceTreeError("Source tree validation failed: " + "; ".join(messages))


@dataclass(frozen=True)
class SourceTreeLayout:
    """Resolved important paths in a Konnaxion source tree."""

    root: Path
    frontend_dir: Path | None
    backend_dir: Path | None
    docker_dir: Path | None
    docs_dir: Path | None
    compose_files: tuple[Path, ...]
    package_json: Path | None
    manage_py: Path | None
    pyproject_toml: Path | None

    def to_metadata(self) -> dict[str, object]:
        return {
            "frontend_dir": str(self.frontend_dir) if self.frontend_dir else "",
            "backend_dir": str(self.backend_dir) if self.backend_dir else "",
            "docker_dir": str(self.docker_dir) if self.docker_dir else "",
            "docs_dir": str(self.docs_dir) if self.docs_dir else "",
            "compose_files": [str(path) for path in self.compose_files],
            "package_json": str(self.package_json) if self.package_json else "",
            "manage_py": str(self.manage_py) if self.manage_py else "",
            "pyproject_toml": str(self.pyproject_toml) if self.pyproject_toml else "",
        }


DEFAULT_IGNORE_PATTERNS = (
    ".git/**",
    ".hg/**",
    ".svn/**",
    ".mypy_cache/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
    ".tox/**",
    ".venv/**",
    "venv/**",
    "env/**",
    "node_modules/**",
    ".next/**",
    "dist/**",
    "build/**",
    "coverage/**",
    "__pycache__/**",
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.swp",
    ".DS_Store",
)

FORBIDDEN_SECRET_PATTERNS = (
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_ed25519",
    "**/id_rsa",
    "**/id_ed25519",
    "**/*secret*",
    "**/*secrets*",
    "**/*credential*",
    "**/*credentials*",
    "**/*token*",
    "**/*private-key*",
    "**/authorized_keys",
    "**/known_hosts",
)

ALLOWED_SECRET_FREE_TEMPLATES = (
    "*.env.template",
    "**/*.env.template",
    "env-templates/**",
    "templates/env/**",
    "example.env",
    ".env.example",
    "**/.env.example",
)

ROOT_MARKER_FILES = (
    "pyproject.toml",
    "package.json",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

FRONTEND_MARKERS = (
    "package.json",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "tsconfig.json",
)

BACKEND_MARKERS = (
    "manage.py",
    "pyproject.toml",
    "requirements.txt",
    "requirements",
)

COMPOSE_FILENAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "docker-compose.production.yml",
    "docker-compose.prod.yml",
    "docker-compose.local.yml",
)

CANONICAL_SERVICE_NAMES = tuple(service.value for service in DockerService)


def inspect_source_tree(
    root: Path | str,
    *,
    include_docs: bool = True,
    extra_ignore_patterns: Sequence[str] = (),
    fail_on_warnings: bool = False,
) -> SourceTreeReport:
    """
    Inspect and validate a Konnaxion source tree.

    Returns a structured report. Call `report.raise_for_errors()` before build
    stages that require a valid source tree.
    """

    root_path = Path(root).expanduser().resolve()

    if not root_path.exists():
        raise SourceTreeError(f"Source root does not exist: {root_path}")

    if not root_path.is_dir():
        raise SourceTreeError(f"Source root is not a directory: {root_path}")

    layout = detect_layout(root_path)
    issues = list(validate_layout(layout))
    ignore_patterns = tuple(DEFAULT_IGNORE_PATTERNS) + tuple(extra_ignore_patterns)

    files = tuple(
        iter_source_files(
            root_path,
            layout=layout,
            include_docs=include_docs,
            ignore_patterns=ignore_patterns,
        )
    )

    issues.extend(validate_no_forbidden_secrets(files))
    issues.extend(validate_capsule_extension_absent(files))
    issues.extend(validate_service_name_hints(files))
    issues.extend(validate_build_markers(layout))

    if fail_on_warnings:
        issues = [
            SourceTreeIssue(
                severity=SourceTreeSeverity.ERROR
                if issue.severity == SourceTreeSeverity.WARNING
                else issue.severity,
                code=issue.code,
                message=issue.message,
                path=issue.path,
                area=issue.area,
            )
            for issue in issues
        ]

    return SourceTreeReport(
        root=str(root_path),
        app_version=APP_VERSION,
        param_version=PARAM_VERSION,
        files=files,
        issues=tuple(issues),
        metadata={
            "builder": BUILDER_NAME,
            "layout": layout.to_metadata(),
            "canonical_services": CANONICAL_SERVICE_NAMES,
            "include_docs": include_docs,
        },
    )


def detect_layout(root: Path) -> SourceTreeLayout:
    """Detect important Konnaxion repository paths."""

    frontend_dir = first_existing_dir(
        root,
        (
            "frontend",
            "apps/frontend",
            "konnaxion-frontend",
            "web",
            "client",
        ),
        markers=FRONTEND_MARKERS,
    )

    if frontend_dir is None and looks_like_frontend_dir(root):
        frontend_dir = root

    backend_dir = first_existing_dir(
        root,
        (
            "backend",
            "apps/backend",
            "konnaxion-backend",
            "server",
            "api",
        ),
        markers=BACKEND_MARKERS,
    )

    if backend_dir is None and looks_like_backend_dir(root):
        backend_dir = root

    docker_dir = first_existing_dir(
        root,
        (
            "docker",
            "compose",
            "deploy",
            "deployment",
            "infra",
        ),
    )

    docs_dir = first_existing_dir(root, ("docs", "documentation"))

    compose_files = tuple(
        sorted(
            path
            for name in COMPOSE_FILENAMES
            for path in root.rglob(name)
            if not should_ignore_path(path.relative_to(root).as_posix(), DEFAULT_IGNORE_PATTERNS)
        )
    )

    package_json = find_first(root, "package.json")
    manage_py = find_first(root, "manage.py")
    pyproject_toml = find_first(root, "pyproject.toml")

    return SourceTreeLayout(
        root=root,
        frontend_dir=frontend_dir,
        backend_dir=backend_dir,
        docker_dir=docker_dir,
        docs_dir=docs_dir,
        compose_files=compose_files,
        package_json=package_json,
        manage_py=manage_py,
        pyproject_toml=pyproject_toml,
    )


def validate_layout(layout: SourceTreeLayout) -> Iterator[SourceTreeIssue]:
    """Validate required source tree layout elements."""

    root_markers = [layout.root / marker for marker in ROOT_MARKER_FILES]

    if not any(path.exists() for path in root_markers):
        yield SourceTreeIssue(
            severity=SourceTreeSeverity.WARNING,
            code="missing_root_marker",
            message="No common project root marker found.",
            path=str(layout.root),
            area=SourceTreeArea.ROOT,
        )

    if layout.frontend_dir is None:
        yield SourceTreeIssue(
            severity=SourceTreeSeverity.ERROR,
            code="missing_frontend",
            message="Could not locate the Next.js frontend source directory.",
            area=SourceTreeArea.FRONTEND,
        )

    if layout.backend_dir is None:
        yield SourceTreeIssue(
            severity=SourceTreeSeverity.ERROR,
            code="missing_backend",
            message="Could not locate the Django backend source directory.",
            area=SourceTreeArea.BACKEND,
        )

    if not layout.compose_files:
        yield SourceTreeIssue(
            severity=SourceTreeSeverity.WARNING,
            code="missing_compose_file",
            message="No Docker Compose file found in source tree.",
            area=SourceTreeArea.DOCKER,
        )


def validate_build_markers(layout: SourceTreeLayout) -> Iterator[SourceTreeIssue]:
    """Validate expected frontend/backend build markers."""

    if layout.frontend_dir is not None:
        package_json = layout.frontend_dir / "package.json"
        if not package_json.exists():
            yield SourceTreeIssue(
                severity=SourceTreeSeverity.ERROR,
                code="missing_frontend_package_json",
                message="Frontend directory does not contain package.json.",
                path=relative_or_absolute(layout.root, package_json),
                area=SourceTreeArea.FRONTEND,
            )

    if layout.backend_dir is not None:
        manage_py = layout.backend_dir / "manage.py"
        if not manage_py.exists():
            nested_manage_py = find_first(layout.backend_dir, "manage.py")
            if nested_manage_py is None:
                yield SourceTreeIssue(
                    severity=SourceTreeSeverity.ERROR,
                    code="missing_backend_manage_py",
                    message="Backend directory does not contain Django manage.py.",
                    path=relative_or_absolute(layout.root, manage_py),
                    area=SourceTreeArea.BACKEND,
                )


def validate_no_forbidden_secrets(files: Iterable[SourceFile]) -> Iterator[SourceTreeIssue]:
    """Reject likely secret-bearing files from capsule inputs."""

    for source_file in files:
        if not source_file.capsule_input:
            continue

        if is_allowed_secret_free_template(source_file.path):
            continue

        if matches_any(source_file.path, FORBIDDEN_SECRET_PATTERNS):
            yield SourceTreeIssue(
                severity=SourceTreeSeverity.ERROR,
                code="forbidden_secret_file",
                message="Potential secret-bearing file must not be included in a capsule.",
                path=source_file.path,
                area=source_file.area,
            )


def validate_capsule_extension_absent(files: Iterable[SourceFile]) -> Iterator[SourceTreeIssue]:
    """Warn if existing `.kxcap` files are present inside source tree."""

    for source_file in files:
        if source_file.path.endswith(CAPSULE_EXTENSION):
            yield SourceTreeIssue(
                severity=SourceTreeSeverity.WARNING,
                code="capsule_artifact_in_source",
                message="Existing capsule artifact found inside source tree.",
                path=source_file.path,
                area=source_file.area,
            )


def validate_service_name_hints(files: Iterable[SourceFile]) -> Iterator[SourceTreeIssue]:
    """
    Warn about files likely to contain non-canonical service aliases.

    Full Compose validation belongs in `kx_builder.manifest` or runtime Compose
    generation, but early hints help keep coded files aligned.
    """

    compose_like_files = [
        file for file in files
        if file.path.endswith((".yml", ".yaml"))
        and (
            "compose" in Path(file.path).name
            or "docker-compose" in Path(file.path).name
        )
    ]

    alias_hints = {
        "backend": DockerService.DJANGO_API.value,
        "api": DockerService.DJANGO_API.value,
        "web": DockerService.FRONTEND_NEXT.value,
        "next": DockerService.FRONTEND_NEXT.value,
        "frontend": DockerService.FRONTEND_NEXT.value,
        "db": DockerService.POSTGRES.value,
        "database": DockerService.POSTGRES.value,
        "cache": DockerService.REDIS.value,
        "worker": DockerService.CELERYWORKER.value,
        "scheduler": DockerService.CELERYBEAT.value,
        "media": DockerService.MEDIA_NGINX.value,
    }

    for source_file in compose_like_files:
        path = Path(source_file.path)
        for alias, canonical in alias_hints.items():
            if alias in path.stem.split("-") or alias in path.stem.split("_"):
                yield SourceTreeIssue(
                    severity=SourceTreeSeverity.WARNING,
                    code="non_canonical_service_alias_hint",
                    message=(
                        f"Potential service alias {alias!r}; prefer canonical "
                        f"service name {canonical!r}."
                    ),
                    path=source_file.path,
                    area=SourceTreeArea.DOCKER,
                )


def iter_source_files(
    root: Path,
    *,
    layout: SourceTreeLayout,
    include_docs: bool,
    ignore_patterns: Sequence[str],
) -> Iterator[SourceFile]:
    """Yield deterministic source file inventory."""

    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        relative_path = file_path.relative_to(root).as_posix()

        if should_ignore_path(relative_path, ignore_patterns):
            continue

        area = classify_path(relative_path, layout)

        if area == SourceTreeArea.DOCS and not include_docs:
            capsule_input = False
        else:
            capsule_input = True

        yield SourceFile(
            path=relative_path,
            area=area,
            size_bytes=file_path.stat().st_size,
            sha256=sha256_file(file_path),
            capsule_input=capsule_input,
        )


def classify_path(relative_path: str, layout: SourceTreeLayout) -> SourceTreeArea:
    """Classify a repository-relative path into a logical source area."""

    path = Path(relative_path)

    if layout.frontend_dir is not None:
        frontend_rel = relative_or_none(layout.root, layout.frontend_dir)
        if frontend_rel and is_relative_to_posix(relative_path, frontend_rel):
            return SourceTreeArea.FRONTEND

    if layout.backend_dir is not None:
        backend_rel = relative_or_none(layout.root, layout.backend_dir)
        if backend_rel and is_relative_to_posix(relative_path, backend_rel):
            return SourceTreeArea.BACKEND

    if layout.docker_dir is not None:
        docker_rel = relative_or_none(layout.root, layout.docker_dir)
        if docker_rel and is_relative_to_posix(relative_path, docker_rel):
            return SourceTreeArea.DOCKER

    if layout.docs_dir is not None:
        docs_rel = relative_or_none(layout.root, layout.docs_dir)
        if docs_rel and is_relative_to_posix(relative_path, docs_rel):
            return SourceTreeArea.DOCS

    if path.name in COMPOSE_FILENAMES or "docker" in path.parts:
        return SourceTreeArea.DOCKER

    if path.name in {"pyproject.toml", "package.json", "pnpm-lock.yaml", "package-lock.json"}:
        return SourceTreeArea.ROOT

    if path.suffix in {".yaml", ".yml", ".toml", ".ini", ".cfg", ".json"}:
        return SourceTreeArea.CONFIG

    return SourceTreeArea.UNKNOWN


def first_existing_dir(
    root: Path,
    candidates: Sequence[str],
    *,
    markers: Sequence[str] = (),
) -> Path | None:
    """Return first candidate directory that exists and optionally has a marker."""

    for candidate in candidates:
        path = root / candidate
        if not path.is_dir():
            continue

        if markers and not any((path / marker).exists() for marker in markers):
            nested_marker = any(find_first(path, marker) for marker in markers)
            if not nested_marker:
                continue

        return path.resolve()

    return None


def find_first(root: Path, name: str) -> Path | None:
    """Find first file by basename while ignoring common dependency/cache dirs."""

    if not root.exists():
        return None

    for path in sorted(root.rglob(name)):
        if not path.is_file():
            continue

        try:
            relative_path = path.relative_to(root).as_posix()
        except ValueError:
            continue

        if should_ignore_path(relative_path, DEFAULT_IGNORE_PATTERNS):
            continue

        return path.resolve()

    return None


def looks_like_frontend_dir(path: Path) -> bool:
    return any((path / marker).exists() for marker in FRONTEND_MARKERS)


def looks_like_backend_dir(path: Path) -> bool:
    return any((path / marker).exists() for marker in BACKEND_MARKERS)


def should_ignore_path(relative_path: str, patterns: Sequence[str]) -> bool:
    """Return True if path matches an ignore pattern."""

    normalized = normalize_posix(relative_path)

    for pattern in patterns:
        pattern = normalize_posix(pattern)
        if fnmatch.fnmatch(normalized, pattern):
            return True

        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True

    return False


def matches_any(relative_path: str, patterns: Sequence[str]) -> bool:
    normalized = normalize_posix(relative_path)
    basename = Path(normalized).name

    for pattern in patterns:
        pattern = normalize_posix(pattern)

        if fnmatch.fnmatch(normalized, pattern):
            return True

        if fnmatch.fnmatch(basename, pattern):
            return True

    return False


def is_allowed_secret_free_template(relative_path: str) -> bool:
    return matches_any(relative_path, ALLOWED_SECRET_FREE_TEMPLATES)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(chunk_size), b""):
            digest.update(chunk)

    return digest.hexdigest()


def normalize_posix(path: str) -> str:
    return str(path).replace(os.sep, "/").replace("\\", "/").strip("/")


def relative_or_none(root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def relative_or_absolute(root: Path, path: Path) -> str:
    relative = relative_or_none(root, path)
    return relative if relative is not None else str(path)


def is_relative_to_posix(relative_path: str, prefix: str) -> bool:
    normalized = normalize_posix(relative_path)
    normalized_prefix = normalize_posix(prefix)

    if normalized == normalized_prefix:
        return True

    return normalized.startswith(normalized_prefix + "/")


def capsule_input_paths(report: SourceTreeReport) -> tuple[str, ...]:
    """Return capsule input paths from a report."""

    return tuple(file.path for file in report.capsule_inputs)


def write_source_tree_report(report: SourceTreeReport, output_path: Path | str) -> Path:
    """Write a JSON source tree report."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.to_json(indent=2) + "\n", encoding="utf-8")
    return output


def load_source_tree_report(path: Path | str) -> SourceTreeReport:
    """Load a JSON report previously written by `write_source_tree_report`."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    files = tuple(
        SourceFile(
            path=item["path"],
            area=SourceTreeArea(item["area"]),
            size_bytes=int(item["size_bytes"]),
            sha256=item["sha256"],
            capsule_input=bool(item.get("capsule_input", True)),
        )
        for item in payload.get("files", [])
    )

    issues = tuple(
        SourceTreeIssue(
            severity=SourceTreeSeverity(item["severity"]),
            code=item["code"],
            message=item["message"],
            path=item.get("path", ""),
            area=SourceTreeArea(item.get("area", SourceTreeArea.UNKNOWN.value)),
        )
        for item in payload.get("issues", [])
    )

    return SourceTreeReport(
        root=payload["root"],
        app_version=payload.get("app_version", APP_VERSION),
        param_version=payload.get("param_version", PARAM_VERSION),
        files=files,
        issues=issues,
        metadata=payload.get("metadata", {}),
    )
