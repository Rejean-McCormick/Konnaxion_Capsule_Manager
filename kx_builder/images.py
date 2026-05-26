"""Image build and export helpers for Konnaxion Capsule Builder.

The Builder creates offline-loadable Docker image archives for canonical
Konnaxion runtime services.

Docker's ``save`` format is a Docker-loadable tar archive. Konnaxion stores
those archives with the canonical ``*.oci.tar`` suffix because the capsule
layout treats them as offline-loadable OCI-style artifacts.

This module intentionally accepts only canonical service names and writes
deterministic image metadata for manifest generation.
"""

from __future__ import annotations

import fnmatch
import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Iterable, Mapping, Sequence

import yaml

from kx_shared.errors import CapsuleBuildError
from kx_shared.konnaxion_constants import (
    APP_VERSION,
    CANONICAL_DOCKER_SERVICES,
    DockerService,
)


IMAGE_ARCHIVE_SUFFIX: Final[str] = ".oci.tar"
IMAGES_DIRNAME: Final[str] = "images"
IMAGE_METADATA_FILENAME: Final[str] = "images.yaml"

# Images the Builder can build directly from the app source tree.
APP_BUILD_SERVICES: Final[frozenset[str]] = frozenset(
    {
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
    }
)

# Keep this broad for backwards compatibility with older callers that may pass
# explicit specs for proxy/static services. Default build specs only build app
# images; proxy/database/cache images are exported from pulled/local images.
BUILDABLE_SERVICES: Final[frozenset[str]] = frozenset(
    {
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.TRAEFIK.value,
        DockerService.MEDIA_NGINX.value,
    }
)

# Runtime services that are not normally built from the app source tree.
RUNTIME_EXTERNAL_SERVICES: Final[frozenset[str]] = frozenset(
    {
        DockerService.TRAEFIK.value,
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.MEDIA_NGINX.value,
    }
)

# Services that reuse the Django image.
DJANGO_IMAGE_ALIAS_SERVICES: Final[frozenset[str]] = frozenset(
    {
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
        DockerService.FLOWER.value,
    }
)

# Services required for the canonical runtime. Flower remains optional.
REQUIRED_RUNTIME_IMAGE_SERVICES: Final[frozenset[str]] = frozenset(
    {
        DockerService.TRAEFIK.value,
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
        DockerService.MEDIA_NGINX.value,
    }
)

OPTIONAL_RUNTIME_IMAGE_SERVICES: Final[frozenset[str]] = frozenset(
    {
        DockerService.FLOWER.value,
    }
)

DEFAULT_EXTERNAL_IMAGES: Final[dict[str, str]] = {
    DockerService.TRAEFIK.value: "traefik:v3.1",
    DockerService.POSTGRES.value: "postgres:16",
    DockerService.REDIS.value: "redis:7",
    DockerService.MEDIA_NGINX.value: "nginx:stable",
}

BACKEND_CLEAN_EXCLUDED_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        "dist",
        "build",
        "media",
        "staticfiles",
        "logs",
    }
)

BACKEND_CLEAN_EXCLUDED_PATTERNS: Final[tuple[str, ...]] = (
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.sqlite3",
    "*.log",
    "*.egg-info",
    ".coverage",
)

FRONTEND_CAPSULE_DOCKERFILE: Final[str] = """\
FROM node:20-alpine AS builder
WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --no-frozen-lockfile

COPY . .

ENV NODE_ENV=production
ENV NODE_OPTIONS=--max-old-space-size=4096

RUN pnpm build

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.* ./
COPY --from=builder /app/env.mjs ./env.mjs

EXPOSE 3000

CMD ["node", "node_modules/next/dist/bin/next", "start", "-H", "0.0.0.0", "-p", "3000"]
"""


@dataclass(frozen=True)
class ImageBuildSpec:
    """Build instructions for one canonical Konnaxion service image."""

    service: str
    image: str
    context: Path
    dockerfile: Path
    build_args: Mapping[str, str] | None = None
    target: str | None = None
    platform: str | None = None
    no_cache: bool = False
    pull: bool = False

    def validate(self) -> None:
        """Validate service, context, and Dockerfile before building."""

        validate_canonical_service(self.service)

        if self.service not in BUILDABLE_SERVICES:
            raise CapsuleBuildError(
                f"Service {self.service!r} is not a Builder-managed image. "
                "Only canonical buildable services may be built/exported by "
                "the capsule builder."
            )

        if not self.context.exists() or not self.context.is_dir():
            raise CapsuleBuildError(f"Image build context does not exist: {self.context}")

        dockerfile = self.resolved_dockerfile
        if not dockerfile.exists() or not dockerfile.is_file():
            raise CapsuleBuildError(f"Dockerfile does not exist: {dockerfile}")

    @property
    def resolved_dockerfile(self) -> Path:
        """Return the Dockerfile path, resolving relative paths from context."""

        if self.dockerfile.is_absolute():
            return self.dockerfile
        return self.context / self.dockerfile


@dataclass(frozen=True)
class BuiltImage:
    """Metadata for a built image."""

    service: str
    image: str
    image_id: str | None = None
    built_at: datetime | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Return a manifest-friendly representation."""

        return {
            "service": self.service,
            "image": self.image,
            "image_id": self.image_id,
            "built_at": (self.built_at or datetime.now(UTC)).isoformat(),
        }


@dataclass(frozen=True)
class ExportedImage:
    """Metadata for an exported image archive."""

    service: str
    image: str
    archive: Path
    sha256: str
    size_bytes: int
    exported_at: datetime | None = None

    def as_dict(self) -> dict[str, str | int]:
        """Return a manifest-friendly representation."""

        return {
            "service": self.service,
            "image": self.image,
            "archive": self.archive.name,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "exported_at": (self.exported_at or datetime.now(UTC)).isoformat(),
        }


def default_image_tag(
    service: str,
    *,
    capsule_id: str,
    app_version: str = APP_VERSION,
) -> str:
    """Return the canonical local image tag for a service in a capsule build."""

    validate_canonical_service(service)
    safe_capsule_id = str(capsule_id).strip()
    safe_app_version = str(app_version).strip() or APP_VERSION

    if not safe_capsule_id:
        raise CapsuleBuildError("capsule_id is required for default image tags.")

    return f"konnaxion/{service}:{safe_app_version}-{safe_capsule_id}"


def default_archive_name(service: str) -> str:
    """Return the canonical image archive filename for a service."""

    validate_canonical_service(service)
    return f"{service}{IMAGE_ARCHIVE_SUFFIX}"


def default_runtime_image_map(
    *,
    capsule_id: str,
    app_version: str = APP_VERSION,
    include_flower: bool = False,
) -> dict[str, str]:
    """Return the default image map for a complete capsule runtime."""

    django_image = default_image_tag(
        DockerService.DJANGO_API.value,
        capsule_id=capsule_id,
        app_version=app_version,
    )
    frontend_image = default_image_tag(
        DockerService.FRONTEND_NEXT.value,
        capsule_id=capsule_id,
        app_version=app_version,
    )

    image_map: dict[str, str] = {
        DockerService.FRONTEND_NEXT.value: frontend_image,
        DockerService.DJANGO_API.value: django_image,
        DockerService.CELERYWORKER.value: django_image,
        DockerService.CELERYBEAT.value: django_image,
        DockerService.TRAEFIK.value: DEFAULT_EXTERNAL_IMAGES[DockerService.TRAEFIK.value],
        DockerService.POSTGRES.value: DEFAULT_EXTERNAL_IMAGES[DockerService.POSTGRES.value],
        DockerService.REDIS.value: DEFAULT_EXTERNAL_IMAGES[DockerService.REDIS.value],
        DockerService.MEDIA_NGINX.value: DEFAULT_EXTERNAL_IMAGES[
            DockerService.MEDIA_NGINX.value
        ],
    }

    if include_flower:
        image_map[DockerService.FLOWER.value] = django_image

    return image_map


def default_image_build_specs(
    *,
    source_root: Path,
    capsule_id: str,
    app_version: str = APP_VERSION,
    work_dir: Path | None = None,
    platform: str | None = None,
    no_cache: bool = False,
    pull: bool = False,
) -> tuple[ImageBuildSpec, ...]:
    """Return default build specs for app-owned runtime images.

    ``source_root`` is the Konnaxion application repo root that contains
    ``backend/`` and ``frontend/``.
    """

    source_root = Path(source_root).expanduser().resolve()
    if not source_root.exists() or not source_root.is_dir():
        raise CapsuleBuildError(f"source_root does not exist: {source_root}")

    backend_root = source_root / "backend"
    frontend_root = source_root / "frontend"

    if not backend_root.exists():
        raise CapsuleBuildError(f"Missing backend source directory: {backend_root}")
    if not frontend_root.exists():
        raise CapsuleBuildError(f"Missing frontend source directory: {frontend_root}")

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="kx-builder-images-"))
    else:
        work_dir = Path(work_dir).expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

    dockerfile_dir = work_dir / "dockerfiles"
    dockerfile_dir.mkdir(parents=True, exist_ok=True)

    backend_context = prepare_clean_backend_context(
        backend_root,
        work_dir=work_dir / "backend-clean",
    )
    frontend_dockerfile = write_frontend_capsule_dockerfile(
        dockerfile_dir / "frontend-next.Dockerfile",
    )

    django_dockerfile = backend_context / "compose" / "production" / "django" / "Dockerfile"
    if not django_dockerfile.exists():
        raise CapsuleBuildError(
            f"Missing production Django Dockerfile in clean backend context: "
            f"{django_dockerfile}"
        )

    return (
        ImageBuildSpec(
            service=DockerService.DJANGO_API.value,
            image=default_image_tag(
                DockerService.DJANGO_API.value,
                capsule_id=capsule_id,
                app_version=app_version,
            ),
            context=backend_context,
            dockerfile=django_dockerfile,
            platform=platform,
            no_cache=no_cache,
            pull=pull,
        ),
        ImageBuildSpec(
            service=DockerService.FRONTEND_NEXT.value,
            image=default_image_tag(
                DockerService.FRONTEND_NEXT.value,
                capsule_id=capsule_id,
                app_version=app_version,
            ),
            context=frontend_root,
            dockerfile=frontend_dockerfile,
            platform=platform,
            no_cache=no_cache,
            pull=pull,
        ),
    )


def prepare_clean_backend_context(
    backend_root: Path,
    *,
    work_dir: Path,
) -> Path:
    """Copy backend source into a clean Docker context.

    This avoids copying local virtualenvs/caches and prevents stale or generated
    files from polluting the production image build.
    """

    backend_root = Path(backend_root).expanduser().resolve()
    work_dir = Path(work_dir).expanduser().resolve()

    if not backend_root.exists() or not backend_root.is_dir():
        raise CapsuleBuildError(f"Backend source directory does not exist: {backend_root}")

    if work_dir.exists():
        shutil.rmtree(work_dir)

    shutil.copytree(
        backend_root,
        work_dir,
        ignore=_backend_copy_ignore,
    )

    models_py = work_dir / "konnaxion" / "ethikos" / "models.py"
    if models_py.exists():
        text = models_py.read_text(encoding="utf-8", errors="replace")
        if "class Migration" in text and "class ArgumentImpactVote" not in text:
            raise CapsuleBuildError(
                "Clean backend context appears corrupted: "
                "konnaxion/ethikos/models.py contains migration content."
            )

    return work_dir


def write_frontend_capsule_dockerfile(path: Path) -> Path:
    """Write the canonical production frontend Dockerfile used by capsules."""

    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FRONTEND_CAPSULE_DOCKERFILE, encoding="utf-8")
    return path


def build_image(spec: ImageBuildSpec) -> BuiltImage:
    """Build one service image using Docker CLI."""

    spec.validate()

    command: list[str] = [
        "docker",
        "build",
        "--file",
        str(spec.resolved_dockerfile),
        "--tag",
        spec.image,
    ]

    if spec.no_cache:
        command.append("--no-cache")

    if spec.pull:
        command.append("--pull")

    if spec.platform:
        command.extend(["--platform", spec.platform])

    if spec.target:
        command.extend(["--target", spec.target])

    for key, value in sorted((spec.build_args or {}).items()):
        command.extend(["--build-arg", f"{key}={value}"])

    command.append(str(spec.context))

    _run_command(tuple(command), action=f"build image for {spec.service}")

    image_id = inspect_image_id(spec.image)
    if not image_id:
        raise CapsuleBuildError(f"Built image is not inspectable: {spec.image}")

    return BuiltImage(
        service=spec.service,
        image=spec.image,
        image_id=image_id,
        built_at=datetime.now(UTC),
    )


def build_images(specs: Sequence[ImageBuildSpec]) -> tuple[BuiltImage, ...]:
    """Build multiple service images."""

    if not specs:
        raise CapsuleBuildError("No image build specs were provided.")

    seen: set[str] = set()
    for spec in specs:
        service = validate_canonical_service(spec.service)
        if service in seen:
            raise CapsuleBuildError(f"Duplicate image build spec for service: {service}")
        seen.add(service)

    return tuple(build_image(spec) for spec in specs)


def export_image(
    image: BuiltImage | str,
    *,
    service: str,
    output_dir: Path,
    pull_missing: bool = True,
) -> ExportedImage:
    """Export one image as a canonical loadable tar archive."""

    service = validate_canonical_service(service)

    image_name = image.image if isinstance(image, BuiltImage) else str(image).strip()
    if not image_name:
        raise CapsuleBuildError("Image name is required for export.")

    ensure_image_available(image_name, pull_missing=pull_missing)

    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / default_archive_name(service)

    command = ("docker", "save", "--output", str(archive), image_name)
    _run_command(command, action=f"export image for {service}")

    if not archive.exists() or not archive.is_file():
        raise CapsuleBuildError(f"Docker did not create expected image archive: {archive}")

    if archive.stat().st_size <= 0:
        raise CapsuleBuildError(f"Docker created an empty image archive: {archive}")

    return ExportedImage(
        service=service,
        image=image_name,
        archive=archive,
        sha256=sha256_file(archive),
        size_bytes=archive.stat().st_size,
        exported_at=datetime.now(UTC),
    )


def export_images(
    built_images: Sequence[BuiltImage],
    *,
    output_dir: Path,
) -> tuple[ExportedImage, ...]:
    """Export multiple built images into a capsule images directory.

    This preserves the historical API: it exports only the images passed in.
    Use ``export_runtime_images`` for a complete runtime image set.
    """

    if not built_images:
        raise CapsuleBuildError("No built images were provided for export.")

    return tuple(
        export_image(
            built,
            service=built.service,
            output_dir=output_dir,
            pull_missing=False,
        )
        for built in built_images
    )


def export_runtime_images(
    image_map: Mapping[str, str],
    *,
    output_dir: Path,
    required_services: Iterable[str] = REQUIRED_RUNTIME_IMAGE_SERVICES,
    include_optional_services: bool = False,
    pull_missing: bool = True,
) -> tuple[ExportedImage, ...]:
    """Export a complete canonical runtime image set.

    ``image_map`` must use canonical service names. Services may share the same
    Docker image tag; each canonical service still receives its own archive so
    manifest verification can reason about service coverage.
    """

    normalized = normalize_runtime_image_map(image_map)

    required = {validate_canonical_service(service) for service in required_services}
    services = set(required)

    if include_optional_services:
        services.update(OPTIONAL_RUNTIME_IMAGE_SERVICES)
    else:
        services.update(service for service in OPTIONAL_RUNTIME_IMAGE_SERVICES if service in normalized)

    missing = sorted(service for service in services if not normalized.get(service))
    if missing:
        raise CapsuleBuildError(
            f"Missing image mapping for required runtime service(s): {', '.join(missing)}"
        )

    exported: list[ExportedImage] = []
    for service in sorted(services):
        exported.append(
            export_image(
                normalized[service],
                service=service,
                output_dir=output_dir,
                pull_missing=pull_missing,
            )
        )

    assert_required_images_present(exported, required_services=required)
    return tuple(exported)


def build_and_export_images(
    specs: Sequence[ImageBuildSpec],
    *,
    capsule_root: Path,
    include_runtime_external: bool = True,
    include_flower: bool = False,
    pull_missing: bool = True,
) -> tuple[ExportedImage, ...]:
    """Build images and export archives into ``<capsule_root>/images``.

    When ``include_runtime_external`` is true, this exports the complete
    canonical runtime set, not only the app images. This is the mode that
    prevents deployable-looking capsules with only ``images/README.json``.
    """

    capsule_root = Path(capsule_root)
    images_dir = capsule_root / IMAGES_DIRNAME

    built = build_images(specs)

    if not include_runtime_external:
        exported = export_images(built, output_dir=images_dir)
        write_image_metadata(exported, capsule_root=capsule_root)
        return exported

    image_map = runtime_image_map_from_built_images(
        built,
        include_flower=include_flower,
    )
    exported = export_runtime_images(
        image_map,
        output_dir=images_dir,
        include_optional_services=include_flower,
        pull_missing=pull_missing,
    )
    write_image_metadata(exported, capsule_root=capsule_root)
    return exported


def build_and_export_default_runtime_images(
    *,
    source_root: Path,
    capsule_root: Path,
    capsule_id: str,
    app_version: str = APP_VERSION,
    work_dir: Path | None = None,
    platform: str | None = None,
    no_cache: bool = False,
    pull: bool = False,
    pull_missing: bool = True,
    include_flower: bool = False,
) -> tuple[ExportedImage, ...]:
    """Build and export the default complete Konnaxion runtime image set."""

    specs = default_image_build_specs(
        source_root=source_root,
        capsule_id=capsule_id,
        app_version=app_version,
        work_dir=work_dir,
        platform=platform,
        no_cache=no_cache,
        pull=pull,
    )

    return build_and_export_images(
        specs,
        capsule_root=capsule_root,
        include_runtime_external=True,
        include_flower=include_flower,
        pull_missing=pull_missing,
    )


def runtime_image_map_from_built_images(
    built_images: Sequence[BuiltImage],
    *,
    include_flower: bool = False,
) -> dict[str, str]:
    """Return a complete runtime image map from built app images."""

    image_map: dict[str, str] = dict(DEFAULT_EXTERNAL_IMAGES)

    for built in built_images:
        service = validate_canonical_service(built.service)
        image_map[service] = built.image

    django_image = image_map.get(DockerService.DJANGO_API.value)
    if django_image:
        image_map[DockerService.CELERYWORKER.value] = django_image
        image_map[DockerService.CELERYBEAT.value] = django_image
        if include_flower:
            image_map[DockerService.FLOWER.value] = django_image

    missing_app = sorted(APP_BUILD_SERVICES.difference(image_map))
    if missing_app:
        raise CapsuleBuildError(
            f"Missing built app image(s): {', '.join(missing_app)}"
        )

    return normalize_runtime_image_map(image_map)


def normalize_runtime_image_map(image_map: Mapping[str, str]) -> dict[str, str]:
    """Validate and normalize a canonical service image mapping."""

    normalized: dict[str, str] = {}

    for service, image in image_map.items():
        service_name = validate_canonical_service(service)

        image_text = str(image).strip()
        if not image_text:
            raise CapsuleBuildError(f"Image for service {service_name} is empty.")
        if ":" not in image_text and "@" not in image_text:
            raise CapsuleBuildError(
                f"Image for service {service_name} must include a tag or digest: "
                f"{image_text!r}"
            )

        normalized[service_name] = image_text

    django_image = normalized.get(DockerService.DJANGO_API.value)
    if django_image:
        normalized.setdefault(DockerService.CELERYWORKER.value, django_image)
        normalized.setdefault(DockerService.CELERYBEAT.value, django_image)

    return normalized


def write_image_metadata(
    exported_images: Sequence[ExportedImage],
    *,
    capsule_root: Path,
) -> Path:
    """Write image metadata used later by manifest/checksum generation."""

    if not exported_images:
        raise CapsuleBuildError("Cannot write image metadata without exported images.")

    capsule_root = Path(capsule_root)
    capsule_root.mkdir(parents=True, exist_ok=True)
    metadata_file = capsule_root / IMAGE_METADATA_FILENAME

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "images": [item.as_dict() for item in sorted(exported_images, key=lambda i: i.service)],
    }

    metadata_file.write_text(
        yaml.safe_dump(payload, sort_keys=True),
        encoding="utf-8",
    )

    return metadata_file


def load_image_metadata(capsule_root: Path) -> tuple[ExportedImage, ...]:
    """Read exported image metadata from ``images.yaml``."""

    capsule_root = Path(capsule_root)
    metadata_file = capsule_root / IMAGE_METADATA_FILENAME
    if not metadata_file.exists():
        raise CapsuleBuildError(f"Missing image metadata file: {metadata_file}")

    raw = yaml.safe_load(metadata_file.read_text(encoding="utf-8")) or {}
    images = raw.get("images")
    if not isinstance(images, list):
        raise CapsuleBuildError(f"Invalid image metadata file: {metadata_file}")

    loaded: list[ExportedImage] = []
    for item in images:
        if not isinstance(item, dict):
            raise CapsuleBuildError(f"Invalid image metadata entry in {metadata_file}")

        service = str(item.get("service", ""))
        validate_canonical_service(service)

        archive_name = str(item.get("archive", ""))
        if not archive_name:
            raise CapsuleBuildError(f"Image metadata entry missing archive: {item}")

        archive = capsule_root / IMAGES_DIRNAME / Path(archive_name).name
        loaded.append(
            ExportedImage(
                service=service,
                image=str(item.get("image", "")),
                archive=archive,
                sha256=str(item.get("sha256", "")),
                size_bytes=int(item.get("size_bytes", 0)),
                exported_at=None,
            )
        )

    return tuple(loaded)


def verify_exported_images(exported_images: Sequence[ExportedImage]) -> None:
    """Verify exported image archives exist and match their SHA-256 digest."""

    if not exported_images:
        raise CapsuleBuildError("No exported images were provided for verification.")

    for item in exported_images:
        validate_canonical_service(item.service)

        if item.archive.suffixes[-2:] != [".oci", ".tar"]:
            raise CapsuleBuildError(
                f"Image archive must use {IMAGE_ARCHIVE_SUFFIX}: {item.archive}"
            )

        if not item.archive.exists() or not item.archive.is_file():
            raise CapsuleBuildError(f"Image archive does not exist: {item.archive}")

        actual_size = item.archive.stat().st_size
        if actual_size <= 0:
            raise CapsuleBuildError(f"Image archive is empty: {item.archive}")

        if item.size_bytes and actual_size != item.size_bytes:
            raise CapsuleBuildError(
                f"Image archive size mismatch for {item.archive}: "
                f"expected {item.size_bytes}, got {actual_size}"
            )

        actual = sha256_file(item.archive)
        if actual != item.sha256:
            raise CapsuleBuildError(
                f"Image archive checksum mismatch for {item.archive}: "
                f"expected {item.sha256}, got {actual}"
            )


def verify_capsule_image_metadata(
    capsule_root: Path,
    *,
    required_services: Iterable[str] = REQUIRED_RUNTIME_IMAGE_SERVICES,
) -> tuple[ExportedImage, ...]:
    """Load and verify capsule image metadata and required archives."""

    exported = load_image_metadata(capsule_root)
    verify_exported_images(exported)
    assert_required_images_present(exported, required_services=required_services)
    return exported


def ensure_image_available(
    image: str,
    *,
    pull_missing: bool = True,
) -> None:
    """Ensure an image exists locally, optionally pulling external images."""

    image = str(image).strip()
    if not image:
        raise CapsuleBuildError("Image name is required.")

    if inspect_image_id(image):
        return

    if pull_missing and _should_pull_missing_image(image):
        _run_command(
            ("docker", "pull", image),
            action=f"pull image {image}",
        )
        if inspect_image_id(image):
            return

    raise CapsuleBuildError(
        f"Docker image is not available locally: {image}. "
        "Build app images first or allow pulling external runtime images."
    )


def inspect_image_id(image: str) -> str | None:
    """Return Docker image ID for a local image tag, if available."""

    command = ("docker", "image", "inspect", image, "--format", "{{.Id}}")
    completed = _run_command(
        command,
        action=f"inspect image {image}",
        allow_failure=True,
    )

    if completed is None or completed.returncode != 0:
        return None

    value = completed.stdout.strip()
    return value or None


def validate_canonical_service(service: str | DockerService) -> str:
    """Return a canonical service name or raise."""

    service_name = service.value if isinstance(service, DockerService) else str(service)

    if service_name not in CANONICAL_DOCKER_SERVICES:
        allowed = ", ".join(CANONICAL_DOCKER_SERVICES)
        raise CapsuleBuildError(
            f"Unknown Konnaxion service: {service_name!r}. Allowed services: {allowed}"
        )

    return service_name


def assert_required_images_present(
    exported_images: Sequence[ExportedImage],
    *,
    required_services: Iterable[str] = REQUIRED_RUNTIME_IMAGE_SERVICES,
) -> None:
    """Ensure required runtime service images are present in capsule output."""

    if not exported_images:
        raise CapsuleBuildError("No exported images were provided.")

    present = {validate_canonical_service(item.service) for item in exported_images}
    required = {validate_canonical_service(service) for service in required_services}

    missing = sorted(required - present)
    if missing:
        raise CapsuleBuildError(
            f"Missing required capsule image archive(s): {', '.join(missing)}"
        )

    for item in exported_images:
        if item.service in required and item.archive.name == "README.json":
            raise CapsuleBuildError(
                f"Invalid image archive for {item.service}: README.json is not "
                "a loadable image archive."
            )


def sha256_file(path: Path) -> str:
    """Return SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_command(
    command: tuple[str, ...],
    *,
    action: str,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str] | None:
    """Run a Docker command without invoking a shell."""

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise CapsuleBuildError("Docker CLI was not found on this host.") from exc

    if completed.returncode != 0 and not allow_failure:
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        raise CapsuleBuildError(
            f"Failed to {action} with exit code {completed.returncode}: {output}"
        )

    return completed


def _should_pull_missing_image(image: str) -> bool:
    """Return whether a missing image should be pulled from a registry."""

    normalized = image.strip().lower()

    # App images are produced by the Builder and should not be pulled from an
    # untrusted or nonexistent remote registry.
    if normalized.startswith("konnaxion/"):
        return False
    if normalized.startswith("localhost/"):
        return False

    return True


def _backend_copy_ignore(directory: str, names: list[str]) -> set[str]:
    """Ignore local-only backend files when preparing Docker build context."""

    ignored: set[str] = set()

    for name in names:
        if name in BACKEND_CLEAN_EXCLUDED_DIRS:
            ignored.add(name)
            continue

        if any(fnmatch.fnmatch(name, pattern) for pattern in BACKEND_CLEAN_EXCLUDED_PATTERNS):
            ignored.add(name)

    return ignored


__all__ = [
    "APP_BUILD_SERVICES",
    "BACKEND_CLEAN_EXCLUDED_DIRS",
    "BACKEND_CLEAN_EXCLUDED_PATTERNS",
    "BUILDABLE_SERVICES",
    "DEFAULT_EXTERNAL_IMAGES",
    "DJANGO_IMAGE_ALIAS_SERVICES",
    "FRONTEND_CAPSULE_DOCKERFILE",
    "IMAGE_ARCHIVE_SUFFIX",
    "IMAGE_METADATA_FILENAME",
    "IMAGES_DIRNAME",
    "OPTIONAL_RUNTIME_IMAGE_SERVICES",
    "REQUIRED_RUNTIME_IMAGE_SERVICES",
    "RUNTIME_EXTERNAL_SERVICES",
    "BuiltImage",
    "ExportedImage",
    "ImageBuildSpec",
    "assert_required_images_present",
    "build_and_export_default_runtime_images",
    "build_and_export_images",
    "build_image",
    "build_images",
    "default_archive_name",
    "default_image_build_specs",
    "default_image_tag",
    "default_runtime_image_map",
    "ensure_image_available",
    "export_image",
    "export_images",
    "export_runtime_images",
    "inspect_image_id",
    "load_image_metadata",
    "normalize_runtime_image_map",
    "prepare_clean_backend_context",
    "runtime_image_map_from_built_images",
    "sha256_file",
    "validate_canonical_service",
    "verify_capsule_image_metadata",
    "verify_exported_images",
    "write_frontend_capsule_dockerfile",
    "write_image_metadata",
]