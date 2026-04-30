"""
Konnaxion Capsule signing and verification.

A Konnaxion Capsule must be signed before distribution and verified before
import. The canonical capsule root contains:

- manifest.yaml
- checksums.txt
- signature.sig

This module signs and verifies a deterministic payload built from
``manifest.yaml`` and ``checksums.txt``. The signature file is a JSON envelope
stored at ``signature.sig`` so the Builder, Agent, CLI, and tests can inspect it
without guessing binary formats.

Default algorithm: Ed25519.

The implementation uses the optional ``cryptography`` package. If it is not
installed, signing and verification fail closed with CapsuleSignatureError.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from kx_shared.errors import (
    CapsuleFormatError,
    CapsuleSignatureError,
    FileMissingError,
    UnsignedCapsuleError,
)
from kx_shared.konnaxion_constants import CAPSULE_EXTENSION


# ---------------------------------------------------------------------
# Canonical files and envelope values
# ---------------------------------------------------------------------


MANIFEST_FILE = "manifest.yaml"
CHECKSUMS_FILE = "checksums.txt"
SIGNATURE_FILE = "signature.sig"

SIGNATURE_SCHEMA_VERSION = "kx-signature/v1"
SIGNATURE_PURPOSE = "konnaxion-capsule"
SIGNING_PAYLOAD_PREFIX = b"KONNAXION-CAPSULE-SIGNATURE-V1\n"


class SignatureAlgorithm(StrEnum):
    ED25519 = "ed25519"


class SignatureStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


# ---------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class SignatureInput:
    """Input files used to create or verify a capsule signature."""

    manifest_path: Path
    checksums_path: Path
    signature_path: Path | None = None

    @classmethod
    def from_capsule_root(cls, capsule_root: str | Path) -> "SignatureInput":
        root = Path(capsule_root)
        return cls(
            manifest_path=root / MANIFEST_FILE,
            checksums_path=root / CHECKSUMS_FILE,
            signature_path=root / SIGNATURE_FILE,
        )

    def validate_unsigned_inputs(self) -> None:
        require_file(self.manifest_path, "manifest")
        require_file(self.checksums_path, "checksums")

    def validate_signed_inputs(self) -> None:
        self.validate_unsigned_inputs()
        if self.signature_path is None:
            raise UnsignedCapsuleError(
                "Capsule signature path is required.",
                {"signature_file": SIGNATURE_FILE},
            )
        require_file(self.signature_path, "signature")


@dataclass(slots=True, frozen=True)
class SignatureEnvelope:
    """JSON envelope stored at signature.sig."""

    schema_version: str
    purpose: str
    algorithm: SignatureAlgorithm
    created_at: str
    payload_sha256: str
    signature_base64: str
    public_key_fingerprint_sha256: str | None = None
    capsule_id: str | None = None
    capsule_version: str | None = None
    signed_files: tuple[str, ...] = (MANIFEST_FILE, CHECKSUMS_FILE)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "purpose": self.purpose,
            "algorithm": self.algorithm.value,
            "created_at": self.created_at,
            "payload_sha256": self.payload_sha256,
            "signature_base64": self.signature_base64,
            "public_key_fingerprint_sha256": self.public_key_fingerprint_sha256,
            "capsule_id": self.capsule_id,
            "capsule_version": self.capsule_version,
            "signed_files": list(self.signed_files),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SignatureEnvelope":
        try:
            algorithm = SignatureAlgorithm(str(payload["algorithm"]))
        except Exception as exc:
            raise CapsuleSignatureError(
                "Unsupported or missing signature algorithm.",
                {"algorithm": payload.get("algorithm")},
            ) from exc

        return cls(
            schema_version=str(payload.get("schema_version", "")),
            purpose=str(payload.get("purpose", "")),
            algorithm=algorithm,
            created_at=str(payload.get("created_at", "")),
            payload_sha256=str(payload.get("payload_sha256", "")),
            signature_base64=str(payload.get("signature_base64", "")),
            public_key_fingerprint_sha256=(
                str(payload["public_key_fingerprint_sha256"])
                if payload.get("public_key_fingerprint_sha256")
                else None
            ),
            capsule_id=str(payload["capsule_id"]) if payload.get("capsule_id") else None,
            capsule_version=str(payload["capsule_version"]) if payload.get("capsule_version") else None,
            signed_files=tuple(str(item) for item in payload.get("signed_files", [])),
            metadata=dict(payload.get("metadata", {})),
        )

    def validate_shape(self) -> None:
        if self.schema_version != SIGNATURE_SCHEMA_VERSION:
            raise CapsuleSignatureError(
                "Unsupported signature schema version.",
                {
                    "expected": SIGNATURE_SCHEMA_VERSION,
                    "received": self.schema_version,
                },
            )

        if self.purpose != SIGNATURE_PURPOSE:
            raise CapsuleSignatureError(
                "Invalid signature purpose.",
                {
                    "expected": SIGNATURE_PURPOSE,
                    "received": self.purpose,
                },
            )

        if self.algorithm != SignatureAlgorithm.ED25519:
            raise CapsuleSignatureError(
                "Unsupported signature algorithm.",
                {"algorithm": self.algorithm.value},
            )

        if not self.payload_sha256 or len(self.payload_sha256) != 64:
            raise CapsuleSignatureError(
                "Invalid payload digest in signature envelope.",
                {"payload_sha256": self.payload_sha256},
            )

        if not self.signature_base64:
            raise CapsuleSignatureError("Signature envelope does not contain a signature.")

        if tuple(self.signed_files) != (MANIFEST_FILE, CHECKSUMS_FILE):
            raise CapsuleSignatureError(
                "Signature envelope signed file list is not canonical.",
                {
                    "expected": [MANIFEST_FILE, CHECKSUMS_FILE],
                    "received": list(self.signed_files),
                },
            )


@dataclass(slots=True, frozen=True)
class SignatureVerificationResult:
    """Result returned by verification helpers."""

    status: SignatureStatus
    valid: bool
    message: str
    envelope: SignatureEnvelope | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "valid": self.valid,
            "message": self.message,
            "envelope": self.envelope.to_dict() if self.envelope else None,
            "details": dict(self.details),
        }


# ---------------------------------------------------------------------
# Key loading and generation
# ---------------------------------------------------------------------


def generate_ed25519_keypair_pem(
    *,
    private_key_password: bytes | None = None,
) -> tuple[bytes, bytes]:
    """Generate an Ed25519 private/public keypair in PEM format."""

    crypto = require_cryptography()
    private_key = crypto["Ed25519PrivateKey"].generate()
    public_key = private_key.public_key()

    encryption_algorithm = (
        crypto["BestAvailableEncryption"](private_key_password)
        if private_key_password
        else crypto["NoEncryption"]()
    )

    private_pem = private_key.private_bytes(
        encoding=crypto["Encoding"].PEM,
        format=crypto["PrivateFormat"].PKCS8,
        encryption_algorithm=encryption_algorithm,
    )
    public_pem = public_key.public_bytes(
        encoding=crypto["Encoding"].PEM,
        format=crypto["PublicFormat"].SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def load_private_key_pem(path: str | Path, *, password: bytes | None = None) -> Any:
    crypto = require_cryptography()
    require_file(Path(path), "private_key")
    try:
        return crypto["load_pem_private_key"](
            Path(path).read_bytes(),
            password=password,
        )
    except Exception as exc:
        raise CapsuleSignatureError(
            "Failed to load Ed25519 private key.",
            {"path": str(path)},
        ) from exc


def load_public_key_pem(path: str | Path) -> Any:
    crypto = require_cryptography()
    require_file(Path(path), "public_key")
    try:
        return crypto["load_pem_public_key"](Path(path).read_bytes())
    except Exception as exc:
        raise CapsuleSignatureError(
            "Failed to load Ed25519 public key.",
            {"path": str(path)},
        ) from exc


def public_key_from_private_key(private_key: Any) -> Any:
    if not hasattr(private_key, "public_key"):
        raise CapsuleSignatureError("Private key object does not expose public_key().")
    return private_key.public_key()


def public_key_fingerprint_sha256(public_key: Any) -> str:
    crypto = require_cryptography()
    try:
        public_der = public_key.public_bytes(
            encoding=crypto["Encoding"].DER,
            format=crypto["PublicFormat"].SubjectPublicKeyInfo,
        )
    except Exception as exc:
        raise CapsuleSignatureError("Failed to serialize public key for fingerprint.") from exc

    return sha256_hex(public_der)


# ---------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------


def sign_capsule_root(
    capsule_root: str | Path,
    private_key: Any,
    *,
    capsule_id: str | None = None,
    capsule_version: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    overwrite: bool = True,
) -> SignatureEnvelope:
    """Sign manifest.yaml and checksums.txt in an extracted capsule root."""

    inputs = SignatureInput.from_capsule_root(capsule_root)
    return sign_signature_input(
        inputs,
        private_key,
        capsule_id=capsule_id,
        capsule_version=capsule_version,
        metadata=metadata,
        overwrite=overwrite,
    )


def sign_signature_input(
    inputs: SignatureInput,
    private_key: Any,
    *,
    capsule_id: str | None = None,
    capsule_version: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    overwrite: bool = True,
) -> SignatureEnvelope:
    """Create signature.sig for a prepared capsule root."""

    inputs.validate_unsigned_inputs()

    if inputs.signature_path is None:
        raise CapsuleSignatureError(
            "Signature output path is required.",
            {"signature_file": SIGNATURE_FILE},
        )

    if inputs.signature_path.exists() and not overwrite:
        raise CapsuleSignatureError(
            "Signature file already exists and overwrite is disabled.",
            {"signature_path": str(inputs.signature_path)},
        )

    crypto = require_cryptography()
    if not isinstance(private_key, crypto["Ed25519PrivateKey"]):
        raise CapsuleSignatureError(
            "Private key must be an Ed25519 private key.",
            {"key_type": type(private_key).__name__},
        )

    payload = build_signing_payload(inputs.manifest_path, inputs.checksums_path)
    signature = private_key.sign(payload)
    public_key = public_key_from_private_key(private_key)

    envelope = SignatureEnvelope(
        schema_version=SIGNATURE_SCHEMA_VERSION,
        purpose=SIGNATURE_PURPOSE,
        algorithm=SignatureAlgorithm.ED25519,
        created_at=now_iso(),
        payload_sha256=sha256_hex(payload),
        signature_base64=base64.b64encode(signature).decode("ascii"),
        public_key_fingerprint_sha256=public_key_fingerprint_sha256(public_key),
        capsule_id=capsule_id,
        capsule_version=capsule_version,
        metadata=metadata or {},
    )

    write_signature_envelope(inputs.signature_path, envelope)
    return envelope


def sign_capsule_root_with_private_key_file(
    capsule_root: str | Path,
    private_key_path: str | Path,
    *,
    private_key_password: bytes | None = None,
    capsule_id: str | None = None,
    capsule_version: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    overwrite: bool = True,
) -> SignatureEnvelope:
    private_key = load_private_key_pem(private_key_path, password=private_key_password)
    return sign_capsule_root(
        capsule_root,
        private_key,
        capsule_id=capsule_id,
        capsule_version=capsule_version,
        metadata=metadata,
        overwrite=overwrite,
    )


# ---------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------


def verify_capsule_root(
    capsule_root: str | Path,
    public_key: Any,
    *,
    require_signature: bool = True,
) -> SignatureVerificationResult:
    """Verify signature.sig for an extracted capsule root."""

    inputs = SignatureInput.from_capsule_root(capsule_root)
    return verify_signature_input(
        inputs,
        public_key,
        require_signature=require_signature,
    )


def verify_signature_input(
    inputs: SignatureInput,
    public_key: Any,
    *,
    require_signature: bool = True,
) -> SignatureVerificationResult:
    try:
        inputs.validate_unsigned_inputs()

        if inputs.signature_path is None or not inputs.signature_path.exists():
            if require_signature:
                raise UnsignedCapsuleError(
                    "Capsule is unsigned.",
                    {"signature_file": SIGNATURE_FILE},
                )
            return SignatureVerificationResult(
                status=SignatureStatus.MISSING,
                valid=False,
                message="Capsule signature is missing.",
            )

        envelope = read_signature_envelope(inputs.signature_path)
        envelope.validate_shape()

        payload = build_signing_payload(inputs.manifest_path, inputs.checksums_path)
        actual_payload_sha256 = sha256_hex(payload)

        if actual_payload_sha256 != envelope.payload_sha256:
            return SignatureVerificationResult(
                status=SignatureStatus.INVALID,
                valid=False,
                message="Signed payload digest does not match current capsule files.",
                envelope=envelope,
                details={
                    "expected_payload_sha256": envelope.payload_sha256,
                    "actual_payload_sha256": actual_payload_sha256,
                },
            )

        verify_ed25519_signature(
            public_key=public_key,
            payload=payload,
            signature=base64.b64decode(envelope.signature_base64),
        )

        fingerprint = public_key_fingerprint_sha256(public_key)
        if envelope.public_key_fingerprint_sha256:
            if envelope.public_key_fingerprint_sha256 != fingerprint:
                return SignatureVerificationResult(
                    status=SignatureStatus.INVALID,
                    valid=False,
                    message="Public key fingerprint does not match signature envelope.",
                    envelope=envelope,
                    details={
                        "expected_public_key_fingerprint_sha256": envelope.public_key_fingerprint_sha256,
                        "actual_public_key_fingerprint_sha256": fingerprint,
                    },
                )

        return SignatureVerificationResult(
            status=SignatureStatus.VALID,
            valid=True,
            message="Capsule signature is valid.",
            envelope=envelope,
            details={"public_key_fingerprint_sha256": fingerprint},
        )

    except UnsignedCapsuleError as exc:
        if require_signature:
            raise
        return SignatureVerificationResult(
            status=SignatureStatus.MISSING,
            valid=False,
            message=str(exc),
            details={"error": exc.to_dict()},
        )
    except CapsuleSignatureError:
        raise
    except Exception as exc:
        raise CapsuleSignatureError(
            "Capsule signature verification failed.",
            {"error": str(exc)},
        ) from exc


def verify_capsule_root_with_public_key_file(
    capsule_root: str | Path,
    public_key_path: str | Path,
    *,
    require_signature: bool = True,
) -> SignatureVerificationResult:
    public_key = load_public_key_pem(public_key_path)
    return verify_capsule_root(
        capsule_root,
        public_key,
        require_signature=require_signature,
    )


def verify_ed25519_signature(
    *,
    public_key: Any,
    payload: bytes,
    signature: bytes,
) -> None:
    crypto = require_cryptography()
    if not isinstance(public_key, crypto["Ed25519PublicKey"]):
        raise CapsuleSignatureError(
            "Public key must be an Ed25519 public key.",
            {"key_type": type(public_key).__name__},
        )

    try:
        public_key.verify(signature, payload)
    except Exception as exc:
        raise CapsuleSignatureError("Ed25519 signature verification failed.") from exc


# ---------------------------------------------------------------------
# Payload and envelope IO
# ---------------------------------------------------------------------


def build_signing_payload(
    manifest_path: str | Path,
    checksums_path: str | Path,
) -> bytes:
    """Build deterministic signing payload.

    Payload format is explicit and length-prefixed to avoid ambiguity:
    PREFIX
    FILE <name> <byte_length>
    <raw bytes>
    FILE <name> <byte_length>
    <raw bytes>
    """

    manifest_path = Path(manifest_path)
    checksums_path = Path(checksums_path)

    require_file(manifest_path, "manifest")
    require_file(checksums_path, "checksums")

    manifest = manifest_path.read_bytes()
    checksums = checksums_path.read_bytes()

    return b"".join(
        (
            SIGNING_PAYLOAD_PREFIX,
            build_payload_part(MANIFEST_FILE, manifest),
            build_payload_part(CHECKSUMS_FILE, checksums),
        )
    )


def build_payload_part(name: str, content: bytes) -> bytes:
    header = f"FILE {name} {len(content)}\n".encode("utf-8")
    return header + content + b"\n"


def write_signature_envelope(path: str | Path, envelope: SignatureEnvelope) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(envelope.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_signature_envelope(path: str | Path) -> SignatureEnvelope:
    path = Path(path)
    if not path.exists():
        raise UnsignedCapsuleError(
            "Capsule signature file is missing.",
            {"signature_path": str(path)},
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CapsuleSignatureError(
            "Signature file is not valid JSON.",
            {"signature_path": str(path), "error": str(exc)},
        ) from exc

    if not isinstance(payload, Mapping):
        raise CapsuleSignatureError(
            "Signature envelope must be a JSON object.",
            {"signature_path": str(path)},
        )

    envelope = SignatureEnvelope.from_dict(payload)
    envelope.validate_shape()
    return envelope


# ---------------------------------------------------------------------
# Capsule path helpers
# ---------------------------------------------------------------------


def require_capsule_file(path: str | Path) -> Path:
    capsule_path = Path(path)
    if capsule_path.suffix != CAPSULE_EXTENSION:
        raise CapsuleFormatError(
            f"Capsule file must use {CAPSULE_EXTENSION} extension.",
            {"path": str(capsule_path), "extension": capsule_path.suffix},
        )
    require_file(capsule_path, "capsule")
    return capsule_path


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileMissingError(
            f"Required {label} file is missing.",
            {"path": str(path)},
        )

    if not path.is_file():
        raise FileMissingError(
            f"Required {label} path is not a file.",
            {"path": str(path)},
        )


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------
# Optional cryptography binding
# ---------------------------------------------------------------------


def require_cryptography() -> dict[str, Any]:
    """Import cryptography primitives or fail closed."""

    try:
        from cryptography.hazmat.primitives.serialization import (  # type: ignore
            BestAvailableEncryption,
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
            load_pem_private_key,
            load_pem_public_key,
        )
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # type: ignore
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except Exception as exc:
        raise CapsuleSignatureError(
            "The cryptography package is required for capsule signing and verification.",
            {"package": "cryptography"},
        ) from exc

    return {
        "BestAvailableEncryption": BestAvailableEncryption,
        "Encoding": Encoding,
        "NoEncryption": NoEncryption,
        "PrivateFormat": PrivateFormat,
        "PublicFormat": PublicFormat,
        "load_pem_private_key": load_pem_private_key,
        "load_pem_public_key": load_pem_public_key,
        "Ed25519PrivateKey": Ed25519PrivateKey,
        "Ed25519PublicKey": Ed25519PublicKey,
    }


__all__ = [
    "CHECKSUMS_FILE",
    "MANIFEST_FILE",
    "SIGNATURE_FILE",
    "SIGNATURE_PURPOSE",
    "SIGNATURE_SCHEMA_VERSION",
    "SIGNING_PAYLOAD_PREFIX",
    "SignatureAlgorithm",
    "SignatureEnvelope",
    "SignatureInput",
    "SignatureStatus",
    "SignatureVerificationResult",
    "build_payload_part",
    "build_signing_payload",
    "generate_ed25519_keypair_pem",
    "load_private_key_pem",
    "load_public_key_pem",
    "now_iso",
    "public_key_fingerprint_sha256",
    "public_key_from_private_key",
    "read_signature_envelope",
    "require_capsule_file",
    "require_cryptography",
    "require_file",
    "sha256_hex",
    "sign_capsule_root",
    "sign_capsule_root_with_private_key_file",
    "sign_signature_input",
    "verify_capsule_root",
    "verify_capsule_root_with_public_key_file",
    "verify_ed25519_signature",
    "verify_signature_input",
    "write_signature_envelope",
]
