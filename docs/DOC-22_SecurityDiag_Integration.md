---
doc_id: DOC-22
title: SecurityDiag Integration Contract
status: implementation-ready
last_updated: 2026-09-05
---

# DOC-22 — SecurityDiag Integration Contract

## Purpose

SecurityDiag and Capsule Manager are complementary security layers. They MUST NOT duplicate privileged enforcement.

```text
SecurityDiag = independent diagnostic / evidence / release qualification
Capsule Manager = orchestration and operator UX
Konnaxion Agent = privileged enforcement boundary
```

## Canonical evidence exchange

After every Agent Security Gate execution, the Agent writes a non-secret evidence snapshot to:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/state/security-gate.json
```

The evidence includes only gate status, per-check status, blocking failures, warnings, runtime-evidence metadata, capsule id and compose path. It MUST NOT include runtime secret values.

SecurityDiag reads this file over its read-only SSH audit channel and cross-checks it against independent host evidence. A Capsule Manager `UNKNOWN`, `SKIPPED`, or `FAIL_BLOCKING` result is release-blocking when Capsule integration is required.

## No assumed security state

The Agent Security Gate MUST NOT inject `True` for signature verification, image checksums, firewall state, backup readiness, admin privacy, PostgreSQL exposure, or Redis exposure. Those values must be derived from artifact/runtime/host evidence.

## Capsule signature trust

Structural verification rejects malformed or placeholder `signature.sig`. Startup qualification additionally performs cryptographic verification against the trusted public key configured by `KX_CAPSULE_PUBLIC_KEY_FILE`, defaulting to:

```text
/opt/konnaxion/agent/keys/capsule-signing-public.pem
```

A missing key or failed signature is blocking.

## Image trust

For Agent startup, the signed capsule manifest is the source of truth for allowed runtime image references. A canonical service name does not by itself authorize an arbitrary image.

## Agent boundary

SecurityDiag expects the Agent to:

- bind only to loopback or a Unix socket;
- use bearer-token authentication;
- run as `kx-agent`;
- keep its token and audit files restricted;
- expose only allowlisted operations;
- keep normal users out of the Docker group;
- persist append-only audit evidence.

## Combined release decision

```text
SecurityDiag technical gate PASS
+ Capsule Manager Security Gate PASS/WARN with no blocking/UNKNOWN checks
+ external exposure PASS
+ restore evidence PASS
+ incident-recovery attestations complete
= SECURITY QUALIFIED FOR RELEASE
```
