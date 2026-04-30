---
doc_id: DOC-13
title: Konnaxion Threat Model
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: draft
owner: Konnaxion Architecture
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-03_Konnaxion_Capsule_Format.md
  - DOC-05_Konnaxion_Agent_Security_Model.md
  - DOC-06_Konnaxion_Network_Profiles.md
  - DOC-07_Konnaxion_Security_Gate.md
  - DOC-08_Konnaxion_Runtime_Docker_Compose.md
---

# DOC-13 — Konnaxion Threat Model

## 0. Purpose

This document defines the canonical threat model for the Konnaxion Capsule architecture.

It covers:

```text
Konnaxion Capsule
Konnaxion Capsule Manager
Konnaxion Agent
Konnaxion Box / Host
Docker Compose Runtime
Konnaxion Instance
Network profiles
Secrets
Backups
Updates / rollback
Public and private exposure modes
```

The goal is not only to describe risks. The goal is to define which risks must be prevented by architecture, which risks must be detected, and which risks must block startup.

---

## 1. Canonical security principle

Konnaxion must be:

```text
private-by-default
deny-by-default
signed-by-default
least-privilege-by-default
recoverable-by-default
```

The user experience target remains plug-and-play, but the system must not let plug-and-play become insecure-by-default.

The user should choose simple modes such as:

```text
Local
Intranet
Private Tunnel
Public Temporary
VPS Public
```

The system translates those choices into firewall rules, routing, container policies, secrets, certificates and health checks.

---

## 2. Security baseline

The Konnaxion threat model assumes the following baseline:

```text
1. The capsule is signed.
2. The capsule contains no real secrets.
3. Secrets are generated on install.
4. Postgres is never exposed publicly.
5. Redis is never exposed publicly.
6. Docker socket is never mounted into application containers.
7. Docker daemon TCP is never exposed.
8. Next.js direct port is never public.
9. Django/Gunicorn direct port is never public.
10. Flower/dashboard surfaces are private only.
11. Traefik is the only public-facing entrypoint.
12. Public mode is never the default.
13. Temporary public mode must expire automatically.
14. The host firewall is deny-by-default.
15. Unknown containers or unknown images are blocking findings.
```

---

## 3. System under threat model

### 3.1 Target architecture

```text
Konnaxion Box / Host
  ├── Konnaxion Capsule Manager
  │     └── User-facing UI
  ├── Konnaxion Agent
  │     └── Privileged local service with allowlisted operations
  ├── Docker Engine / Compose Runtime
  │     └── Konnaxion Instance
  │           ├── traefik
  │           ├── frontend-next
  │           ├── django-api
  │           ├── media-nginx
  │           ├── postgres
  │           ├── redis
  │           ├── celeryworker
  │           └── celerybeat
  └── Host security layer
        ├── firewall
        ├── updates
        ├── logs
        ├── backups
        └── monitoring
```

### 3.2 Canonical runtime routing

```text
https://<HOST>/        -> frontend-next
https://<HOST>/api/    -> django-api
https://<HOST>/admin/  -> django-api
https://<HOST>/media/  -> media-nginx
```

### 3.3 Internal-only services

```text
postgres
redis
celeryworker
celerybeat
flower, unless explicitly enabled in private mode
```

---

## 4. Trust boundaries

| Boundary | Description | Trust level |
|---|---|---|
| User browser → Traefik | User traffic enters Konnaxion | Untrusted |
| Traefik → frontend-next | Internal reverse proxy traffic | Controlled |
| Traefik → django-api | Internal reverse proxy traffic | Controlled |
| django-api → postgres | Application data path | Sensitive |
| django-api → redis | Job/broker path | Sensitive |
| celeryworker → postgres/redis | Background processing path | Sensitive |
| Manager UI → Agent | Local management API | Sensitive |
| Agent → Docker Engine | Privileged orchestration path | Critical |
| Agent → firewall | Privileged network control | Critical |
| Capsule file → Manager | Supply-chain input | Untrusted until verified |
| Backup archive → restore flow | Recovery input | Untrusted until verified |
| Tunnel provider → Traefik | Temporary exposure path | Untrusted external edge |

The most sensitive trust boundary is:

```text
Konnaxion Agent -> Docker / firewall / host system
```

The Agent must not behave like a generic shell or unrestricted Docker frontend.

---

## 5. Assets to protect

### 5.1 Critical assets

| Asset | Why it matters |
|---|---|
| `DJANGO_SECRET_KEY` | Session/signing security |
| `POSTGRES_PASSWORD` | Database access |
| `DATABASE_URL` | Full DB connection authority |
| Admin credentials | Full platform control |
| API tokens | External service access |
| Private keys | Identity and encryption |
| PostgreSQL data | Core user/platform data |
| Media uploads | User files and content |
| Capsule signing key | Supply-chain root of trust |
| Konnaxion Agent control API | Privileged local control |
| Backup archives | Full data recovery material |
| Docker Engine access | Root-equivalent in many setups |
| Network profile state | Determines exposure level |

### 5.2 Sensitive operational assets

```text
logs
crash dumps
.env files
capsule manifests
healthcheck output
backup metadata
public tunnel URLs
temporary admin credentials
```

Logs must never print full secrets.

---

## 6. Attacker profiles

| Actor | Capability | Primary concern |
|---|---|---|
| Internet scanner | Finds open ports and weak services | Exposed dashboards, DB, Redis, SSH |
| Opportunistic bot | Exploits known CVEs / weak configs | Container compromise, web exploit |
| Malicious capsule distributor | Ships modified `.kxcap` | Supply-chain compromise |
| Local network attacker | Same LAN as Konnaxion Box | Intranet sniffing, admin UI abuse |
| Compromised admin workstation | Has access to Manager UI or capsule files | Credential theft, malicious deploy |
| Malicious insider | Has physical or local access | Export data, alter config |
| Malware on host | Attempts persistence and credential theft | Cron/systemd/backdoor persistence |
| Misconfigured operator | Accidentally exposes internal ports | Repeat of public attack surface |
| Compromised tunnel token | Opens unintended public access | Persistent public exposure |

---

## 7. Historical incident assumptions

The previous VPS incident proves the threat model must assume:

```text
1. A server can be compromised during deployment.
2. Docker can be abused to run malicious containers.
3. Cron can be used for persistence.
4. Temporary directories can hide malware.
5. A malicious user/backdoor can be attempted.
6. Secrets on the host can be exposed.
7. Cleanup is not equivalent to trust restoration.
8. Rebuild from clean source is the long-term recovery path.
```

Therefore, Konnaxion Capsule architecture must prefer:

```text
clean rebuild
signed artifacts
secret rotation
known images only
known containers only
known ports only
verified backups only
```

---

## 8. Attack surfaces

### 8.1 External network

| Surface | Threat | Required control |
|---|---|---|
| `80/tcp` | HTTP downgrade / ACME path abuse | Redirect to HTTPS, minimal middleware |
| `443/tcp` | App exploit surface | Traefik only, security headers |
| Public tunnel | Accidental public exposure | Expiration, auth, audit log |
| SSH | Brute force / stolen key | Disabled by default for Box, key-only for VPS |
| Admin UI | Account takeover | MFA recommended, rate limits, private by default |

### 8.2 Internal network

| Surface | Threat | Required control |
|---|---|---|
| Postgres | Data theft/destruction | Internal Docker network only |
| Redis | Job injection / data leakage | Internal Docker network only |
| Celery worker | Code execution via job payloads | Authenticated app-only access |
| Flower/dashboard | Operational leak/control | Disabled or private only |
| Docker network | Lateral movement | Dedicated isolated network per instance |

### 8.3 Host

| Surface | Threat | Required control |
|---|---|---|
| Docker socket | Root-equivalent host control | Never mounted into app containers |
| Docker group | Root-equivalent for users | Avoid broad membership |
| Systemd services | Persistence | Known service allowlist |
| Cron | Persistence | Monitor and verify |
| `/tmp`, `/dev/shm` | Malware staging | Monitor known IoCs, no trust in old host |
| Firewall | Exposure drift | Managed by Agent, audited |
| Backups | Malware preservation | Data-only backup policy |

### 8.4 Capsule supply chain

| Surface | Threat | Required control |
|---|---|---|
| `.kxcap` file | Tampering | Signature required |
| `manifest.yaml` | Port/image/volume abuse | Schema + policy validation |
| OCI images | Malicious code | Checksums + allowlist |
| env templates | Default secrets | No real secrets, no insecure defaults |
| migration scripts | Destructive schema/code actions | Declared, reviewed, logged |
| seed data | Embedded malicious payloads | Sanitize and size-limit |

### 8.5 Manager / Agent

| Surface | Threat | Required control |
|---|---|---|
| Manager UI | CSRF/local web abuse | Local auth token, loopback binding |
| Agent API | Privileged action abuse | mTLS or local socket ACLs |
| Agent command execution | Arbitrary shell execution | No generic shell endpoint |
| Docker calls | Unknown privileged containers | Policy allowlist |
| Network mode changes | Unsafe exposure | Security Gate before applying |
| Update flow | Malicious capsule update | Verify before switch |

---

## 9. STRIDE model

### 9.1 Spoofing

| Threat | Example | Control |
|---|---|---|
| Fake capsule | Attacker provides modified `.kxcap` | Signature verification |
| Fake Manager UI | Phishing local admin page | Signed app, local URL clarity |
| Fake service | Rogue container named like official service | Service/image allowlist |
| Fake admin | Stolen admin credential | MFA, password rotation, audit |

Blocking controls:

```text
KX_REQUIRE_SIGNED_CAPSULE=true
KX_ALLOW_UNKNOWN_IMAGES=false
KX_SECURITY_GATE_REQUIRED=true
```

### 9.2 Tampering

| Threat | Example | Control |
|---|---|---|
| Manifest edited | Adds public Postgres port | Schema + policy validation |
| Image replaced | Modified backend image | Checksum validation |
| Env file altered | Enables DEBUG or weak secrets | Security Gate checks |
| Firewall altered | Opens `3000` or `5432` | Drift detection |
| Backup altered | Restore malicious data/config | Restore verification |

Blocking conditions:

```text
manifest_schema = FAIL_BLOCKING
image_checksums = FAIL_BLOCKING
dangerous_ports_blocked = FAIL_BLOCKING
secrets_not_default = FAIL_BLOCKING
```

### 9.3 Repudiation

| Threat | Example | Control |
|---|---|---|
| Operator denies enabling public tunnel | Missing audit log | Append-only event log |
| Capsule source unclear | No provenance | Capsule metadata + signature |
| Security override unclear | Manual change not tracked | Change log with reason |
| Admin account action unclear | Lack of audit trail | App-level audit events |

Required event log fields:

```yaml
timestamp:
actor:
instance_id:
action:
network_profile:
result:
security_gate_result:
capsule_id:
capsule_version:
```

### 9.4 Information disclosure

| Threat | Example | Control |
|---|---|---|
| Secrets in logs | `.env` dumped to support log | Secret redaction |
| DB exposed | `5432` bound publicly | Internal network only |
| Redis exposed | `6379` public | Internal network only |
| Admin dashboard public | Flower/Traefik dashboard visible | Private only |
| Backup leak | Unencrypted dump copied | Protected backup path |
| Analytics re-identification | Small cohort export | k-anonymity and export limits |

### 9.5 Denial of service

| Threat | Example | Control |
|---|---|---|
| Public bot traffic | Overloads demo box | Rate limit / temporary public only |
| Heavy frontend build | Exhausts RAM | Prebuilt capsule images |
| Redis exhaustion | Job flood | Queue limits, internal only |
| Disk exhaustion | Logs/backups fill disk | Retention policy |
| CPU miner | Malicious process | Known process/container monitoring |
| Failed migration | App down after update | Backup + rollback |

### 9.6 Elevation of privilege

| Threat | Example | Control |
|---|---|---|
| Docker group abuse | User gains root-level host control | No broad Docker group access |
| Privileged container | Container escapes/is too powerful | `privileged: false`, blocked |
| Host network | Container bypasses network isolation | `network_mode: host` blocked |
| Docker socket mount | Container controls Docker | Mount blocked |
| Agent shell endpoint | UI becomes root shell | No generic command API |
| Backdoor user | Malicious local sudo user | User/service allowlist checks |

Blocking policies:

```yaml
allow_privileged_containers: false
allow_host_network: false
allow_docker_socket_mount: false
allow_unknown_images: false
allow_unknown_containers: false
```

---

## 10. Threat scenarios and required responses

### T01 — User imports a modified capsule

**Scenario:** A `.kxcap` has been altered after build.

**Impact:** Supply-chain compromise.

**Required detection:**

```text
signature invalid
checksum mismatch
manifest hash mismatch
```

**Required response:**

```text
FAIL_BLOCKING
Do not import.
Do not extract images.
Do not start instance.
Show "Capsule verification failed."
```

---

### T02 — Capsule tries to expose Postgres

**Scenario:** `docker-compose.capsule.yml` includes:

```text
5432:5432
```

**Impact:** Direct database exposure.

**Required response:**

```text
FAIL_BLOCKING
Reject capsule or profile.
```

**Canonical rule:**

```text
Postgres must be internal only in every profile.
```

---

### T03 — Capsule tries to mount Docker socket

**Scenario:** A service attempts:

```text
/var/run/docker.sock:/var/run/docker.sock
```

**Impact:** Container can control Docker and likely host.

**Required response:**

```text
FAIL_BLOCKING
```

**Canonical rule:**

```text
Application containers must never mount Docker socket.
```

---

### T04 — Operator enables public temporary mode and forgets it

**Scenario:** Public tunnel remains open.

**Impact:** Demo becomes public long-term.

**Required controls:**

```text
expiration required
max duration enforced
auto-close timer
audit event
visible status in UI
```

**Required response after expiry:**

```text
close tunnel
return to previous private profile
log event
show status: public expired
```

---

### T05 — Host firewall drift opens internal ports

**Scenario:** A manual firewall change exposes `3000`, `5432`, `6379`, `5555` or `8000`.

**Impact:** Direct service exposure.

**Required detection:**

```text
scheduled security check
pre-start check
network profile check
```

**Required response:**

```text
FAIL_BLOCKING if startup
WARN or auto-remediate if running
show "Firewall drift detected"
```

---

### T06 — Unknown container appears

**Scenario:** Docker shows a container not declared by the active capsule.

**Impact:** Possible compromise or operator drift.

**Required response:**

```text
instance status = degraded or security_blocked
show unknown container name/image
prevent update/start until resolved
```

For a Konnaxion Box, unknown containers should be treated as suspicious by default.

---

### T07 — Secrets appear in logs

**Scenario:** `.env`, `DATABASE_URL`, `DJANGO_SECRET_KEY` or API tokens are printed.

**Impact:** Credential disclosure.

**Required response:**

```text
redact in Manager UI
flag security warning
recommend secret rotation
prevent uploading raw logs through support export
```

---

### T08 — Restore from old compromised disk

**Scenario:** Operator tries to restore full disk image or old Docker volumes after compromise.

**Impact:** Malware and persistence restored.

**Required response:**

```text
block as unsupported recovery path
allow only DB dump + media restore
require new secrets
require clean capsule
```

Canonical restore policy:

```text
restore data, not machines
restore verified data, not runtime state
```

---

### T09 — Malicious cron/systemd persistence

**Scenario:** Host contains unknown cron or systemd entries.

**Impact:** Malware persistence.

**Required detection:**

```text
host integrity check
known service allowlist
cron scan
```

**Required response:**

```text
security_blocked for public modes
degraded for private modes unless manually accepted
```

---

### T10 — Manager UI abused by local webpage

**Scenario:** A browser page tries to call the Manager local API.

**Impact:** Local privilege escalation through browser.

**Required controls:**

```text
Manager API bound to loopback or Unix socket
CSRF protection
random local auth token
Origin checks
no unauthenticated privileged actions
```

---

## 11. Network profile threat controls

### 11.1 `local_only`

| Risk | Control |
|---|---|
| Accidental LAN exposure | Bind to `127.0.0.1` only |
| Browser abuse | Local auth token |
| Public cert confusion | Use local cert or HTTP loopback only |

Required:

```text
KX_EXPOSURE_MODE=private
No public tunnel
No LAN bind
No router instructions
```

### 11.2 `intranet_private`

| Risk | Control |
|---|---|
| Same-LAN attacker | HTTPS, admin auth |
| Accidental WAN exposure | No router port forwarding |
| mDNS spoofing | Clear host fingerprint / local cert warning handling |

Required:

```text
Bind 443 on LAN interface
Block all internal service ports
Show LAN URL
Do not configure public DNS
```

### 11.3 `private_tunnel`

| Risk | Control |
|---|---|
| Unauthorized tunnel user | Tunnel access policy |
| Stale device access | Tailnet/device review |
| Token leak | Token storage protection |

Required:

```text
No public router port
Tunnel identity required
Visible status in Manager
```

### 11.4 `public_temporary`

| Risk | Control |
|---|---|
| Forgotten exposure | Expiration required |
| Link sharing | Optional access password/auth |
| Abuse traffic | Rate limit / max duration |
| Misleading status | Prominent UI banner |

Required:

```text
KX_PUBLIC_MODE_ENABLED=true
KX_PUBLIC_MODE_EXPIRES_AT required
Max duration enforced
Auto-close required
```

### 11.5 `public_vps`

| Risk | Control |
|---|---|
| Internet scanning | Cloud firewall + UFW |
| SSH brute force | key-only, restricted IP |
| Public dashboard | dashboard disabled/private |
| Server compromise | backups, updates, monitoring |
| Secrets on host | secret rotation, no logs |

Required:

```text
80/443 public
22 restricted
3000/5432/6379/5555/8000 blocked
Docker TCP blocked
```

---

## 12. Required Security Gate checks

The Security Gate must run:

```text
before import
before first start
before profile change
before public temporary mode
before update
before restore
on scheduled health checks
```

### 12.1 Blocking checks

| Check | Blocking condition |
|---|---|
| `capsule_signature` | invalid, missing, unknown signer |
| `manifest_schema` | invalid or unsupported version |
| `image_checksums` | mismatch |
| `allowed_images_only` | unknown image |
| `dangerous_ports_blocked` | public/internal forbidden port exposed |
| `postgres_not_public` | Postgres published |
| `redis_not_public` | Redis published |
| `docker_socket_not_mounted` | socket mounted |
| `no_privileged_containers` | `privileged: true` |
| `no_host_network` | `network_mode: host` |
| `secrets_present` | required secret missing after install |
| `secrets_not_default` | default placeholder secret |
| `public_mode_expiry` | missing expiry for public temporary |
| `unknown_containers` | unknown running container in managed namespace |
| `agent_policy_valid` | Agent would execute unallowlisted action |

### 12.2 Warning checks

| Check | Warning condition |
|---|---|
| `backup_configured` | backup disabled in local-only mode |
| `host_updates` | updates pending |
| `disk_space` | below warning threshold |
| `log_retention` | not configured |
| `admin_mfa` | not enabled |
| `monitoring_configured` | missing optional alerts |

---

## 13. Container policy

Every service in `docker-compose.capsule.yml` must satisfy:

```yaml
privileged: false
read_only: true where possible
restart: unless-stopped
networks:
  - konnaxion_internal
```

Disallowed patterns:

```yaml
network_mode: host
privileged: true
pid: host
ipc: host
volumes:
  - /:/host
  - /var/run/docker.sock:/var/run/docker.sock
ports:
  - "5432:5432"
  - "6379:6379"
  - "3000:3000"
  - "5555:5555"
  - "8000:8000"
```

Allowed published ports by profile:

```yaml
local_only:
  - 127.0.0.1:443:443

intranet_private:
  - <LAN_IP>:443:443

private_tunnel:
  - 127.0.0.1:443:443

public_temporary:
  - 127.0.0.1:443:443

public_vps:
  - 0.0.0.0:80:80
  - 0.0.0.0:443:443
```

---

## 14. Secret handling policy

### 14.1 Required generated secrets

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
KX_INSTANCE_SECRET
KX_LOCAL_MANAGER_TOKEN
initial admin password or invite token
tunnel token, if enabled
backup encryption key, if enabled
```

### 14.2 Rules

```text
1. Capsules contain templates only.
2. Real secrets are generated on install.
3. Secrets are stored under the instance, not inside the capsule.
4. Secrets must not be printed in logs.
5. Secret export requires explicit user action.
6. Secret rotation must be supported.
7. Restore must not reuse compromised secrets by default.
```

### 14.3 Redaction patterns

The Manager and Agent logs must redact:

```text
DATABASE_URL=
POSTGRES_PASSWORD=
DJANGO_SECRET_KEY=
SECRET_KEY=
API_KEY=
TOKEN=
PRIVATE_KEY=
BEGIN RSA PRIVATE KEY
BEGIN OPENSSH PRIVATE KEY
```

---

## 15. Backup and restore threat model

### 15.1 Backup scope

Allowed backup contents:

```text
Postgres dump
media/uploads
instance metadata
sanitized manifest
non-secret configuration snapshot
```

Protected or encrypted backup contents:

```text
secrets
admin recovery token
tunnel config
backup key material
```

Disallowed backup contents:

```text
entire old disk
/tmp
/dev/shm
unknown Docker volumes
old crontabs
old systemd units
old authorized_keys
old sudoers files
malware cleanup workspace
```

### 15.2 Restore controls

Before restore:

```text
verify backup metadata
verify capsule compatibility
scan for disallowed paths
generate or rotate secrets unless explicitly preserving
run migration dry-run if possible
take pre-restore snapshot
```

After restore:

```text
run Security Gate
run app healthchecks
verify no internal ports are public
verify admin login
verify migrations
```

---

## 16. Update and rollback threat model

### 16.1 Update risks

```text
malicious capsule update
schema migration failure
incompatible seed data
partial image load
old secrets carried forward unsafely
public mode state retained unexpectedly
rollback disabled by destructive migration
```

### 16.2 Required update flow

```text
1. Verify new capsule.
2. Backup database and media.
3. Check migration plan.
4. Load images.
5. Start new stack or update stack.
6. Run migrations.
7. Run healthchecks.
8. Switch active capsule.
9. Keep previous capsule available for rollback.
10. If failure, rollback automatically where safe.
```

### 16.3 Rollback constraints

Rollback is allowed only if:

```text
previous capsule exists
backup exists
migration compatibility is known
Security Gate passes after rollback
network profile remains safe
```

---

## 17. Logging and monitoring

### 17.1 Required logs

```text
Agent action log
Manager UI event log
Security Gate results
Network profile changes
Public tunnel open/close events
Capsule import/verify events
Backup/restore events
Update/rollback events
Unknown container findings
Firewall drift findings
```

### 17.2 Log requirements

```text
structured JSON preferred
timestamps in UTC
instance_id included
capsule_id included
actor included when known
result included
no raw secrets
```

Example:

```json
{
  "timestamp": "2026-04-30T17:30:00Z",
  "event": "network_profile_changed",
  "instance_id": "demo-001",
  "actor": "local_admin",
  "from": "intranet_private",
  "to": "public_temporary",
  "expires_at": "2026-04-30T19:30:00Z",
  "security_gate": "PASS"
}
```

---

## 18. Incident response model

### 18.1 Severity levels

| Severity | Meaning | Example |
|---|---|---|
| `SEV-1` | Active compromise or public critical exposure | Unknown container + public DB |
| `SEV-2` | Serious security drift | Firewall opened internal port |
| `SEV-3` | Contained risk | Backup disabled |
| `SEV-4` | Low-risk warning | Updates pending |

### 18.2 Automatic responses

| Finding | Response |
|---|---|
| Unknown container | Mark instance `security_blocked` |
| Public Postgres/Redis | Block startup, close profile change |
| Invalid capsule signature | Reject import |
| Missing public expiry | Reject public mode |
| Docker socket mount | Reject capsule |
| Privileged container | Reject capsule |
| Host network | Reject capsule |
| Secret in logs | Redact + recommend rotation |
| Firewall drift | Auto-remediate if Manager owns firewall |

### 18.3 Manual recovery principle

If host compromise is suspected:

```text
Do not harden the same host as final fix.
Do not clone the disk.
Do not restore old Docker volumes blindly.
Rebuild from clean capsule/source.
Restore only verified data.
Rotate secrets.
```

---

## 19. Risk register

| ID | Risk | Likelihood | Impact | Rating | Required mitigation |
|---|---|---:|---:|---:|---|
| R01 | Public exposure of Postgres | Medium | Critical | High | Blocking port policy |
| R02 | Public exposure of Redis | Medium | Critical | High | Blocking port policy |
| R03 | Docker socket exposed | Low | Critical | High | Compose policy validation |
| R04 | Malicious capsule | Medium | Critical | High | Signature + checksums |
| R05 | Unknown container compromise | Medium | Critical | High | Container allowlist |
| R06 | Secret leakage in logs | Medium | High | High | Redaction + rotation |
| R07 | Forgotten public tunnel | Medium | High | High | Mandatory expiry |
| R08 | Host firewall drift | Medium | High | High | Drift detection |
| R09 | Weak/default secrets | Medium | High | High | Generated secrets only |
| R10 | Backup preserves malware | Medium | High | High | Data-only backups |
| R11 | Failed update/migration | Medium | Medium | Medium | Backup + rollback |
| R12 | LAN attacker abuses intranet mode | Medium | Medium | Medium | HTTPS + auth |
| R13 | Admin credential theft | Medium | High | High | MFA + rotation |
| R14 | Denial of service on demo box | Medium | Medium | Medium | public temporary limits |
| R15 | Misuse of Agent API | Low | Critical | High | Allowlisted API only |

---

## 20. Non-goals

This threat model does not attempt to solve:

```text
nation-state adversaries
physical hardware tampering by a skilled attacker
full endpoint compromise of every admin device
zero-day vulnerabilities in the OS or Docker Engine
formal compliance certification
multi-tenant hostile SaaS isolation
```

Konnaxion Capsule is designed for:

```text
local demos
private intranet deployment
temporary public demos
small production VPS deployments
controlled organizational environments
```

It is not yet designed as a hardened multi-tenant public cloud platform.

---

## 21. MVP security acceptance criteria

A Konnaxion Capsule MVP is not acceptable unless all of the following pass:

```text
[ ] Invalid capsule signatures are rejected.
[ ] Capsule contains no real secrets.
[ ] Install generates new secrets.
[ ] Postgres is not public.
[ ] Redis is not public.
[ ] Docker socket is not mounted.
[ ] Privileged containers are blocked.
[ ] Host network mode is blocked.
[ ] Unknown images are blocked.
[ ] Unknown containers trigger security status.
[ ] Public temporary mode requires expiry.
[ ] Public temporary mode auto-closes.
[ ] Manager UI shows active network profile.
[ ] Manager UI shows security status.
[ ] Security Gate can block startup.
[ ] Backup contains data only, not full host runtime.
[ ] Restore runs Security Gate after completion.
[ ] Logs redact known secret patterns.
```

---

## 22. Test cases

### 22.1 Capsule validation tests

```text
TC-13-001: Import unsigned capsule -> FAIL_BLOCKING
TC-13-002: Import capsule with invalid checksum -> FAIL_BLOCKING
TC-13-003: Import capsule with unsupported manifest version -> FAIL_BLOCKING
TC-13-004: Import capsule with unknown image -> FAIL_BLOCKING
TC-13-005: Import capsule with Docker socket mount -> FAIL_BLOCKING
TC-13-006: Import capsule with privileged container -> FAIL_BLOCKING
TC-13-007: Import capsule with host network -> FAIL_BLOCKING
```

### 22.2 Network tests

```text
TC-13-101: local_only binds only to localhost
TC-13-102: intranet_private exposes only 443 on LAN
TC-13-103: public_temporary requires expires_at
TC-13-104: public_temporary closes after expiry
TC-13-105: public_vps exposes only 80/443 publicly
TC-13-106: postgres is unreachable from host public interface
TC-13-107: redis is unreachable from host public interface
TC-13-108: port 3000 is not public
TC-13-109: port 5555 is not public
```

### 22.3 Runtime tests

```text
TC-13-201: Unknown container triggers security_blocked
TC-13-202: Unknown image triggers security warning/block
TC-13-203: Firewall drift is detected
TC-13-204: Secret pattern is redacted from logs
TC-13-205: Backup does not include /tmp or /dev/shm
TC-13-206: Restore rejects backup with disallowed paths
TC-13-207: Failed update rolls back where safe
```

---

## 23. Canonical policy snippets

### 23.1 Security policy

```yaml
security:
  private_by_default: true
  deny_by_default: true
  require_signed_capsule: true
  generate_secrets_on_install: true
  allow_unknown_images: false
  allow_unknown_containers: false
  allow_privileged_containers: false
  allow_host_network: false
  allow_docker_socket_mount: false
  expose_database: false
  expose_redis: false
  expose_frontend_direct: false
  expose_django_direct: false
```

### 23.2 Public temporary policy

```yaml
public_temporary:
  enabled_by_default: false
  require_expiration: true
  max_duration_hours: 8
  require_security_gate_pass: true
  auto_close_on_expiry: true
  show_visible_banner: true
```

### 23.3 Port policy

```yaml
blocked_public_ports:
  - 3000
  - 5000
  - 5432
  - 6379
  - 5555
  - 8000

allowed_public_ports_by_profile:
  local_only: []
  intranet_private:
    - 443
  private_tunnel: []
  public_temporary: []
  public_vps:
    - 80
    - 443
```

---

## 24. Documentation alignment rules

Any future document that mentions security, capsule import, runtime, ports, Docker, secrets, backups, updates, public mode, or intranet mode must align with this threat model.

A future document must not introduce:

```text
a public database port
a public Redis port
a public direct Next.js port
a public direct Django/Gunicorn port
a non-expiring public temporary mode
real secrets inside capsules
unverified capsules
unknown images by default
Docker socket mounts
privileged containers
host network containers
```

Any exception requires a formal architecture decision record.

---

## 25. Summary

The Konnaxion threat model is built around one product requirement:

```text
Konnaxion must feel plug-and-play, but behave like a locked-down appliance.
```

The architecture therefore uses:

```text
signed capsules
generated secrets
deny-by-default network policy
strict Docker policy
Security Gate blocking checks
private-by-default network profiles
temporary public exposure with expiry
data-only backups
clean rebuild recovery
```

This is the security foundation for Konnaxion Capsule, Konnaxion Capsule Manager, Konnaxion Agent and Konnaxion Box.
