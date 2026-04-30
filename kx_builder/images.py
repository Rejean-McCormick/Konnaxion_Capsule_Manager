"""Image build and export helpers for Konnaxion Capsule Builder.

The Builder creates offline-loadable OCI image archives for canonical
Konnaxion runtime services. This module intentionally accepts only canonical
service names and writes deterministic image metadata for manifest generation.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Iterable, Sequence

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

BUILDABLE_SERVICES: Final[frozenset[str]] = frozenset(
    {
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.TRAEFIK.value,
        DockerService.MEDIA_NGINX.value,
    }
)

RUNTIME_EXTERNAL_SERVICES: Final[frozenset[str]] = frozenset(
    {
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
        DockerService.FLOWER.value,
    }
)


@dataclass(frozen=True)
class ImageBuildSpec:
    """Build instructions for one canonical Konnaxion service image."""

    service: str
    image: str
    context: Path
    dockerfile: Path
    build_args: dict[str, str] | None = None
    target: str | None = None
    platform: str | None = None

    def validate(self) -> None:
        """Validate service, context, and Dockerfile before building."""

        validate_canonical_service(self.service)

        if self.service not in BUILDABLE_SERVICES:
            raise CapsuleBuildError(
                f"Service {self.service!r} is not a Builder-managed image. "
                "Only frontend-next, django-api, traefik, and media-nginx are "
                "built/exported by the MVP capsule builder."
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
    """Metadata for an exported OCI image archive."""

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


def default_image_tag(service: str, *, capsule_id: str, app_version: str = APP_VERSION) -> str:
    """Return the canonical local image tag for a service in a capsule build."""

    validate_canonical_service(service)
    return f"konnaxion/{service}:{app_version}-{capsule_id}"


def default_archive_name(service: str) -> str:
    """Return the canonical OCI archive filename for a service."""

    validate_canonical_service(service)
    return f"{service}{IMAGE_ARCHIVE_SUFFIX}"


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

    if spec.platform:
        command.extend(["--platform", spec.platform])

    if spec.target:
        command.extend(["--target", spec.target])

    for key, value in sorted((spec.build_args or {}).items()):
        command.extend(["--build-arg", f"{key}={value}"])

    command.append(str(spec.context))

    _run_command(tuple(command), action=f"build image for {spec.service}")

    image_id = inspect_image_id(spec.image)

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

    return tuple(build_image(spec) for spec in specs)


def export_image(
    image: BuiltImage | str,
    *,
    service: str,
    output_dir: Path,
) -> ExportedImage:
    """Export one image as a canonical OCI-compatible tar archive.

    Docker's ``save`` output is a loadable image tar archive. The capsule names
    it ``*.oci.tar`` to match the Konnaxion capsule layout.
    """

    validate_canonical_service(service)

    image_name = image.image if isinstance(image, BuiltImage) else image
    if not image_name:
        raise CapsuleBuildError("Image name is required for export.")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / default_archive_name(service)

    command = ("docker", "save", "--output", str(archive), image_name)
    _run_command(command, action=f"export image for {service}")

    if not archive.exists() or not archive.is_file():
        raise CapsuleBuildError(f"Docker did not create expected image archive: {archive}")

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
    """Export multiple built images into the capsule images directory."""

    if not built_images:
        raise CapsuleBuildError("No built images were provided for export.")

    return tuple(
        export_image(
            built,
            service=built.service,
            output_dir=output_dir,
        )
        for built in built_images
    )


def build_and_export_images(
    specs: Sequence[ImageBuildSpec],
    *,
    capsule_root: Path,
) -> tuple[ExportedImage, ...]:
    """Build images and export them into ``<capsule_root>/images``."""

    images_dir = capsule_root / IMAGES_DIRNAME
    built = build_images(specs)
    exported = export_images(built, output_dir=images_dir)
    write_image_metadata(exported, capsule_root=capsule_root)
    return exported


def write_image_metadata(
    exported_images: Sequence[ExportedImage],
    *,
    capsule_root: Path,
) -> Path:
    """Write image metadata used later by manifest/checksum generation."""

    capsule_root.mkdir(parents=True, exist_ok=True)
    metadata_file = capsule_root / IMAGE_METADATA_FILENAME

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "images": [item.as_dict() for item in exported_images],
    }

    metadata_file.write_text(
        yaml.safe_dump(payload, sort_keys=True),
        encoding="utf-8",
    )

    return metadata_file


def load_image_metadata(capsule_root: Path) -> tuple[ExportedImage, ...]:
    """Read exported image metadata from ``images.yaml``."""

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

        archive = capsule_root / IMAGES_DIRNAME / archive_name
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
    """Verify that exported image archives exist and match their SHA-256 digest."""

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

        actual = sha256_file(item.archive)
        if actual != item.sha256:
            raise CapsuleBuildError(
                f"Image archive checksum mismatch for {item.archive}: "
                f"expected {item.sha256}, got {actual}"
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

    service_name = service.value if isinstance(service, DockerService) else service

    if service_name not in CANONICAL_DOCKER_SERVICES:
        allowed = ", ".join(CANONICAL_DOCKER_SERVICES)
        raise CapsuleBuildError(
            f"Unknown Konnaxion service: {service_name!r}. Allowed services: {allowed}"
        )

    return service_name


def assert_required_images_present(
    exported_images: Sequence[ExportedImage],
    *,
    required_services: Iterable[str] = BUILDABLE_SERVICES,
) -> None:
    """Ensure required buildable service images are present in capsule output."""

    present = {item.service for item in exported_images}
    required = set(required_services)

    missing = sorted(required - present)
    if missing:
        raise CapsuleBuildError(
            f"Missing required capsule image archive(s): {', '.join(missing)}"
        )


def sha256_file(path: Path) -> str:
    """Return SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
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
