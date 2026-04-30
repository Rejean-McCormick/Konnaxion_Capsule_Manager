---
doc_id: DOC-07
title: Konnaxion Security Gate
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: draft
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-03_Konnaxion_Capsule_Format.md
  - DOC-04_Konnaxion_Manager_Architecture.md
  - DOC-05_Konnaxion_Agent_Security_Model.md
  - DOC-06_Konnaxion_Network_Profiles.md
---

# DOC-07 — Konnaxion Security Gate

## 1. Purpose

The **Konnaxion Security Gate** is the mandatory safety checkpoint executed by the **Konnaxion Capsule Manager** and **Konnaxion Agent** before a **Konnaxion Instance** can start, update, expose itself on a network, import a capsule, or enable a temporary public tunnel.

The Security Gate exists to make unsafe deployment states difficult or impossible.

It validates:

```text
Capsule integrity
Manifest validity
Image integrity
Runtime policy
Secrets policy
Network exposure
Firewall state
Container isolation
Backup readiness
Update/rollback safety
```

The Security Gate is **blocking by design**. If a critical rule fails, the instance must not start.

---

## 2. Design Principle

```text
Default security posture:
private-by-default
deny-by-default
signed-capsules-only
dangerous-ports-blocked
no-secrets-in-capsule
no-public-internals
```

The manager must never ask the user to manually configure Docker, ports, firewall, Traefik, Redis, Postgres, or secrets during normal plug-and-play usage.

The user chooses a safe network profile. The Security Gate enforces the rest.

---

## 3. Scope

The Security Gate applies to these operations:

| Operation | Gate Required |
|---|---:|
| Import `.kxcap` capsule | yes |
| Create new `Konnaxion Instance` | yes |
| Start instance | yes |
| Change `KX_NETWORK_PROFILE` | yes |
| Enable `KX_PUBLIC_MODE_ENABLED=true` | yes |
| Update instance to new capsule | yes |
| Restore backup | yes |
| Run migrations | yes |
| Expose tunnel | yes |
| Switch to `public_vps` profile | yes |

The Security Gate is not optional.

---

## 4. Canonical Status Values

Each check returns exactly one status.

| Status | Meaning | Blocks start? |
|---|---|---:|
| `PASS` | Check passed | no |
| `WARN` | Risk detected but not fatal for current profile | no |
| `FAIL_BLOCKING` | Critical rule failed | yes |
| `SKIPPED` | Not applicable for current profile | no |
| `UNKNOWN` | Could not verify state | yes, unless explicitly allowlisted |

Default rule:

```text
UNKNOWN = FAIL_BLOCKING
```

Exception: a check may return `UNKNOWN` as non-blocking only if the manifest explicitly marks it as optional for the current profile.

---

## 5. Security Gate Execution Points

### 5.1 Import-time gate

Executed before accepting a `.kxcap`.

Checks:

```text
capsule_signature
capsule_checksums
manifest_schema
manifest_version
allowed_services_only
allowed_images_only
no_embedded_runtime_secrets
```

### 5.2 Install-time gate

Executed before creating an instance.

Checks:

```text
host_requirements
required_directories
instance_id_valid
secrets_generation_policy
volume_policy
backup_policy
```

### 5.3 Start-time gate

Executed before launching containers.

Checks:

```text
secrets_present
secrets_not_default
docker_available
container_policy
network_policy
firewall_policy
dangerous_ports_blocked
```

### 5.4 Exposure-change gate

Executed before switching network profile or enabling public access.

Checks:

```text
network_profile_valid
exposure_mode_valid
public_mode_expiry_required
public_mode_auth_required
allowed_public_ports
dangerous_ports_blocked
admin_surface_private
```

### 5.5 Update-time gate

Executed before applying a new capsule.

Checks:

```text
backup_before_update
new_capsule_signature
new_capsule_checksums
migration_plan_present
rollback_target_present
healthcheck_plan_present
```

---

## 6. Mandatory Check List

These are the canonical Security Gate checks.

```text
capsule_signature
capsule_checksums
manifest_schema
manifest_version
allowed_services_only
allowed_images_only
no_embedded_runtime_secrets

host_requirements
required_directories
instance_id_valid
docker_available
agent_permission_model
filesystem_permissions

secrets_present
secrets_not_default
secrets_generated_locally
secrets_file_permissions
no_secrets_in_logs

container_policy
no_privileged_containers
no_host_network
docker_socket_not_mounted
read_only_root_where_possible
restricted_capabilities
no_unknown_containers

network_profile_valid
exposure_mode_valid
allowed_public_ports
dangerous_ports_blocked
postgres_not_public
redis_not_public
frontend_direct_not_public
django_direct_not_public
flower_not_public
admin_surface_private

firewall_enabled
firewall_deny_default
firewall_profile_matches_network_profile

backup_configured
backup_before_update
rollback_target_present

healthchecks_defined
healthchecks_passing
```

---

## 7. Blocking Rules

The following conditions always produce `FAIL_BLOCKING`.

### 7.1 Capsule Integrity

```text
Invalid capsule signature
Missing signature
Checksum mismatch
Unknown manifest schema
Unsupported capsule version
Unknown image not declared in manifest
Image digest mismatch
```

### 7.2 Secrets

```text
DJANGO_SECRET_KEY missing
DJANGO_SECRET_KEY is default/demo value
POSTGRES_PASSWORD missing
POSTGRES_PASSWORD is default/demo value
DATABASE_URL points outside the instance without explicit allowlist
Any private key bundled in the capsule
Any full .env file with real secrets bundled in the capsule
```

### 7.3 Container Policy

```text
privileged: true
network_mode: host
Docker socket mounted into any container
Unknown container attached to Konnaxion network
Unknown image running under Konnaxion instance
Host root filesystem mounted
Container attempts to bind dangerous public ports
```

### 7.4 Network Exposure

```text
Postgres exposed publicly
Redis exposed publicly
Next.js direct port exposed publicly
Django/Gunicorn direct port exposed publicly
Flower/dashboard exposed publicly
Docker daemon exposed over TCP
Public mode enabled without expiry
Public temporary mode enabled without auth
```

### 7.5 Firewall

```text
Firewall disabled in intranet_private, private_tunnel, public_temporary, or public_vps
Firewall permits dangerous public ports
Firewall does not match selected network profile
Inbound default policy is allow
```

### 7.6 Update Safety

```text
Update requested without backup
Migration plan missing
Rollback target missing
Healthcheck plan missing
New capsule fails signature/checksum validation
```

---

## 8. Canonical Dangerous Ports

These ports must never be exposed publicly.

| Port | Service | Rule |
|---:|---|---|
| `3000` | `frontend-next` direct | never public |
| `5000` | `django-api` / Gunicorn | never public |
| `5432` | `postgres` | never public |
| `6379` | `redis` | never public |
| `5555` | `flower` / dashboard | never public |
| `8000` | Django dev/server direct | never public |
| Docker TCP | Docker daemon | never public |

Only the reverse proxy may be exposed.

```text
Allowed public entrypoint:
Traefik on 443
Traefik on 80 only for HTTP-to-HTTPS redirect or certificate challenge
```

---

## 9. Network Profile Rules

### 9.1 `local_only`

| Rule | Expected |
|---|---|
| Public access | disabled |
| LAN access | disabled |
| Bind address | `127.0.0.1` |
| Allowed ports | local loopback only |
| Public tunnel | disabled |
| Firewall required | recommended |

Blocking:

```text
Any non-loopback bind without explicit profile change
Any public tunnel
Any exposed internal service
```

### 9.2 `intranet_private`

| Rule | Expected |
|---|---|
| Public access | disabled |
| LAN access | enabled |
| Bind address | LAN interface only |
| Allowed ports | `443`, optional `80` redirect |
| Public tunnel | disabled |
| Firewall required | yes |

Blocking:

```text
WAN exposure detected
Router port-forward detected or declared
Postgres/Redis/Django/Next direct exposed
```

### 9.3 `private_tunnel`

| Rule | Expected |
|---|---|
| Public access | disabled |
| VPN access | enabled |
| Allowed provider | Tailscale or approved equivalent |
| Router port-forward | none |
| Public tunnel | disabled unless profile changed |
| Firewall required | yes |

Blocking:

```text
Open public inbound port
Unapproved tunnel provider
Tunnel without ACL/auth
Internal service reachable outside tunnel
```

### 9.4 `public_temporary`

| Rule | Expected |
|---|---|
| Public access | temporary |
| Expiry | required |
| Auth | required |
| Allowed ports | provider tunnel or `443` |
| Max duration | `KX_PUBLIC_MODE_DURATION_HOURS <= 8` |
| Firewall required | yes |

Blocking:

```text
Missing expiry
Missing auth
Duration exceeds policy
Direct public exposure of internal service
```

### 9.5 `public_vps`

| Rule | Expected |
|---|---|
| Public access | enabled |
| Allowed ports | `80`, `443`, restricted `22` |
| Reverse proxy | required |
| Cloud firewall | recommended |
| Local firewall | required |
| Password SSH | forbidden |
| Root SSH | forbidden |

Blocking:

```text
Password SSH enabled
Root SSH enabled
Dangerous public ports open
Firewall disabled
No reverse proxy
```

---

## 10. Required Manifest Security Section

Every `.kxcap` manifest must include a `security` section.

```yaml
security:
  require_signed_capsule: true
  generate_secrets_on_install: true
  allow_unknown_images: false
  allow_privileged_containers: false
  allow_host_network: false
  allow_docker_socket_mount: false
  allow_public_internals: false
  require_firewall: true
  default_network_profile: intranet_private
  default_exposure_mode: private

public_mode:
  enabled_by_default: false
  require_expiration: true
  require_auth: true
  max_duration_hours: 8

blocked_ports:
  - 3000
  - 5000
  - 5432
  - 6379
  - 5555
  - 8000
```

If the section is missing, the Security Gate returns:

```text
manifest_schema = FAIL_BLOCKING
```

---

## 11. Security Gate Report Schema

The Security Gate must produce a machine-readable report.

```yaml
security_gate_report:
  report_version: 1
  generated_at: "2026-04-30T00:00:00Z"
  instance_id: "demo-001"
  capsule_id: "konnaxion-v14-demo-2026.04.30"
  capsule_version: "2026.04.30-demo.1"
  app_version: "v14"
  network_profile: "intranet_private"
  exposure_mode: "private"
  overall_status: "PASS"
  blocking_count: 0
  warning_count: 0

  checks:
    - id: "capsule_signature"
      status: "PASS"
      severity: "critical"
      message: "Capsule signature is valid."
      remediation: ""

    - id: "postgres_not_public"
      status: "PASS"
      severity: "critical"
      message: "PostgreSQL is reachable only inside the Docker network."
      remediation: ""

    - id: "firewall_enabled"
      status: "PASS"
      severity: "critical"
      message: "Firewall is active and matches intranet_private profile."
      remediation: ""
```

Allowed `overall_status` values:

```text
PASS
WARN
FAIL_BLOCKING
```

Rule:

```text
If any check has status FAIL_BLOCKING, overall_status = FAIL_BLOCKING.
If no blocking checks exist but one or more WARN checks exist, overall_status = WARN.
If all required checks pass or are skipped correctly, overall_status = PASS.
```

---

## 12. Severity Levels

| Severity | Meaning |
|---|---|
| `critical` | Must block if failed |
| `high` | Usually blocks outside `local_only` |
| `medium` | Warning unless profile requires blocking |
| `low` | Informational or hygiene warning |

Examples:

| Check | Severity |
|---|---|
| `capsule_signature` | `critical` |
| `postgres_not_public` | `critical` |
| `docker_socket_not_mounted` | `critical` |
| `firewall_enabled` | `critical` outside `local_only` |
| `backup_configured` | `high` |
| `healthchecks_passing` | `high` |
| `no_secrets_in_logs` | `medium` |
| `read_only_root_where_possible` | `medium` |

---

## 13. CLI Commands

The canonical CLI is `kx`.

```bash
kx security check demo-001
kx security check demo-001 --profile intranet_private
kx security report demo-001 --format yaml
kx security report demo-001 --format json
kx security explain demo-001 postgres_not_public
```

Start must implicitly run the gate:

```bash
kx instance start demo-001 --network intranet_private
```

Equivalent internal flow:

```text
1. kx security check demo-001 --profile intranet_private
2. if PASS or allowed WARN: continue
3. if FAIL_BLOCKING: refuse start
4. start instance
5. run healthchecks
6. emit final security report
```

---

## 14. UI Requirements

The Konnaxion Capsule Manager must expose a simple security view.

### 14.1 Healthy state

```text
Security: OK
Network profile: Intranet privé
Exposure: Private
Public access: Disabled

[Open Konnaxion]
[View Security Report]
[Backup]
[Stop]
```

### 14.2 Warning state

```text
Security: Warning
Issue: Backup retention is shorter than recommended.
Konnaxion can start, but this should be corrected.

[Start Anyway]
[Fix Backup Settings]
[View Details]
```

### 14.3 Blocking state

```text
Security: Blocked
Issue: PostgreSQL is exposed outside the internal Docker network.
Konnaxion cannot start until this is fixed.

[Fix Automatically]
[View Details]
[Export Report]
```

The UI must not offer a normal “ignore and start” button for `FAIL_BLOCKING`.

---

## 15. Auto-Fix Policy

Some checks may support automatic remediation.

| Check | Auto-fix allowed |
|---|---:|
| `firewall_enabled` | yes |
| `dangerous_ports_blocked` | yes |
| `secrets_present` | yes, if missing and instance not initialized |
| `secrets_not_default` | yes, rotate with confirmation |
| `backup_configured` | yes |
| `postgres_not_public` | yes, if caused by generated compose config |
| `redis_not_public` | yes, if caused by generated compose config |
| `capsule_signature` | no |
| `image_checksums` | no |
| `unknown_image` | no |
| `docker_socket_not_mounted` | yes, if caused by generated config |
| `unknown_container` | no, requires operator review |

Auto-fix must create an audit entry.

```yaml
audit_event:
  event_type: "security_autofix"
  check_id: "dangerous_ports_blocked"
  instance_id: "demo-001"
  action: "Removed public binding for port 5432."
  actor: "kx-agent"
  result: "success"
```

---

## 16. Audit Log

Every Security Gate run must be logged.

Canonical path:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/logs/security-gate.log
```

Machine-readable report path:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/state/security-gate-report.yaml
```

Audit fields:

```yaml
audit:
  event_id: "sec_20260430_000001"
  event_type: "security_gate_run"
  generated_at: "2026-04-30T00:00:00Z"
  instance_id: "demo-001"
  profile: "intranet_private"
  result: "PASS"
  blocking_count: 0
  warning_count: 0
```

Do not log secret values.

Allowed:

```text
DJANGO_SECRET_KEY present: yes
POSTGRES_PASSWORD present: yes
```

Forbidden:

```text
DJANGO_SECRET_KEY=actual_value
POSTGRES_PASSWORD=actual_value
DATABASE_URL=postgres://user:password@...
```

---

## 17. Canonical Error Codes

| Code | Meaning |
|---|---|
| `KXSEC-001` | Capsule signature invalid |
| `KXSEC-002` | Capsule checksum mismatch |
| `KXSEC-003` | Manifest schema invalid |
| `KXSEC-010` | Secret missing |
| `KXSEC-011` | Default or weak secret |
| `KXSEC-020` | Dangerous public port exposed |
| `KXSEC-021` | Database exposed |
| `KXSEC-022` | Redis exposed |
| `KXSEC-023` | Docker socket exposed |
| `KXSEC-024` | Privileged container requested |
| `KXSEC-025` | Host network requested |
| `KXSEC-030` | Firewall disabled |
| `KXSEC-031` | Firewall profile mismatch |
| `KXSEC-040` | Public mode expiry missing |
| `KXSEC-041` | Public mode auth missing |
| `KXSEC-050` | Backup missing before update |
| `KXSEC-051` | Rollback target missing |
| `KXSEC-060` | Unknown container detected |
| `KXSEC-061` | Unknown image detected |

---

## 18. Example Blocking Report

```yaml
security_gate_report:
  report_version: 1
  instance_id: "demo-001"
  network_profile: "intranet_private"
  exposure_mode: "private"
  overall_status: "FAIL_BLOCKING"
  blocking_count: 2
  warning_count: 0

  checks:
    - id: "postgres_not_public"
      code: "KXSEC-021"
      status: "FAIL_BLOCKING"
      severity: "critical"
      message: "PostgreSQL is bound to 0.0.0.0:5432."
      remediation: "Remove the public port binding and keep Postgres on the internal Docker network only."

    - id: "dangerous_ports_blocked"
      code: "KXSEC-020"
      status: "FAIL_BLOCKING"
      severity: "critical"
      message: "Dangerous public port detected: 5432."
      remediation: "Apply the intranet_private firewall profile."
```

---

## 19. Example Passing Report

```yaml
security_gate_report:
  report_version: 1
  instance_id: "demo-001"
  network_profile: "intranet_private"
  exposure_mode: "private"
  overall_status: "PASS"
  blocking_count: 0
  warning_count: 0

  checks:
    - id: "capsule_signature"
      status: "PASS"
      severity: "critical"

    - id: "allowed_public_ports"
      status: "PASS"
      severity: "critical"

    - id: "postgres_not_public"
      status: "PASS"
      severity: "critical"

    - id: "redis_not_public"
      status: "PASS"
      severity: "critical"

    - id: "docker_socket_not_mounted"
      status: "PASS"
      severity: "critical"

    - id: "firewall_enabled"
      status: "PASS"
      severity: "critical"
```

---

## 20. Implementation Notes

The Security Gate should be implemented in the **Konnaxion Agent**, not only in the UI.

Reason:

```text
The UI can be bypassed.
The Agent controls privileged operations.
Therefore the Agent must enforce the policy.
```

The UI may display and explain the report, but the Agent owns enforcement.

Recommended internal modules:

```text
kx-agent/security/gate
kx-agent/security/checks/capsule
kx-agent/security/checks/secrets
kx-agent/security/checks/network
kx-agent/security/checks/firewall
kx-agent/security/checks/docker
kx-agent/security/checks/backup
kx-agent/security/reporting
```

---

## 21. Non-Goals

DOC-07 does not define:

```text
The full `.kxcap` file format
The full Konnaxion Agent permission model
The full network profile implementation
The backup storage engine
The UI design system
The incident response runbook
```

Those are covered by neighboring documents.

---

## 22. Acceptance Criteria

DOC-07 is implemented when:

```text
A capsule cannot be imported without signature/checksum validation.
A Konnaxion Instance cannot start if a critical check fails.
Postgres and Redis cannot be exposed publicly by generated config.
Docker socket cannot be mounted by generated config.
Privileged containers are rejected.
Host networking is rejected.
Public temporary mode requires auth and expiry.
Every start produces a security report.
Every update requires backup and rollback target.
The UI clearly shows PASS/WARN/FAIL_BLOCKING.
The Agent enforces the policy even if the UI is bypassed.
```

---

## 23. Canonical Summary

```text
DOC-07 defines the Security Gate:
a blocking validation layer enforced by Konnaxion Agent before import, install, start, update, restore, network profile changes, or public exposure.

Default outcome:
safe private deployment.

Unsafe outcome:
blocked before launch.
```
