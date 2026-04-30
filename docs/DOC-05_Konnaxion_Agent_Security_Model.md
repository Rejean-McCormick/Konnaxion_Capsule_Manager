---
doc_id: DOC-05
title: Konnaxion Agent Security Model
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: draft
owner: Konnaxion Architecture
last_updated: 2026-04-30
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-02_Konnaxion_Capsule_Architecture.md
  - DOC-03_Konnaxion_Capsule_Format.md
  - DOC-04_Konnaxion_Manager_Architecture.md
  - DOC-06_Konnaxion_Network_Profiles.md
  - DOC-07_Konnaxion_Security_Gate.md
---

# DOC-05 — Konnaxion Agent Security Model

## 1. Purpose

This document defines the security model for **Konnaxion Agent**, the privileged local service used by **Konnaxion Capsule Manager** to install, verify, configure, start, stop, update, and monitor **Konnaxion Instances**.

The Agent exists because Konnaxion needs controlled access to privileged host operations:

- create local directories under `/opt/konnaxion`
- verify and import `.kxcap` capsules
- load approved Docker/OCI images
- generate secrets
- create Docker networks and volumes
- apply network profiles
- enforce firewall rules
- start and stop the Konnaxion runtime
- run health checks and security checks
- backup, restore, update, and rollback instances

The Agent must make Konnaxion plug-and-play without giving the UI, user, or capsule unlimited system control.

Konnaxion’s runtime stack includes a Next.js frontend, Django + DRF backend, PostgreSQL, Celery, Redis, Traefik, and media/static serving; therefore the Agent controls multiple services and must enforce safe network exposure by default. This stack is defined canonically in `DOC-00_Konnaxion_Canonical_Variables.md` and implemented by the runtime model in `DOC-08_Konnaxion_Runtime_Docker_Compose.md`.

---

## 2. Security rationale

The Agent security model is based on the 2026-04 incident recovery lessons.

The previous VPS was compromised during deployment. Observed compromise indicators included malicious Docker image `negoroo/amco:123`, containers `amco_*`, a miner process, `/tmp/sshd`, `/dev/shm/*`, deploy-user crontab persistence, `pakchoi` user creation attempts, and `/etc/sudoers.d/99-pakchoi`. The recovery notes explicitly state that the server should not be trusted long-term and that the correct fix is a clean rebuild, no disk clone, rotated secrets, SSH keys only, firewall hardening, and public exposure limited to `22`, `80`, and `443`.

The Agent must therefore be designed as a **security boundary**, not merely a deployment helper.

---

## 3. Canonical component relationship

```text
Konnaxion Capsule Manager
  ↓ local authenticated API
Konnaxion Agent
  ↓ allowlisted privileged operations
Host OS / firewall / Docker Engine
  ↓ controlled runtime
Konnaxion Instance
```

The Manager is the user-facing interface.

The Agent is the local privileged service.

The Capsule is the portable application bundle.

The Instance is the installed runtime with data, secrets, logs, backups, and state.

---

## 4. Primary rule

The Agent must be:

```text
private-by-default
deny-by-default
allowlist-driven
signed-capsule-only
least-privilege-oriented
auditable
rollback-safe
```

The Agent must not behave like a general-purpose remote shell, Docker dashboard, or root automation tool.

---

## 5. Non-goals

The Agent is not:

```text
a generic Docker manager
a replacement for Portainer
a remote administration tool
a shell execution service
a general CI/CD runner
a Kubernetes orchestrator
a public API server
a user management system for Konnaxion itself
```

The Agent manages only **Konnaxion-approved operations**.

---

## 6. Trust boundaries

## 6.1 Trusted

The following may be trusted after verification:

```text
Konnaxion Agent binary installed from trusted source
Konnaxion Capsule Manager binary installed from trusted source
signed .kxcap files with valid signature
host OS after clean install
allowlisted Docker/OCI images with matching checksums
locally generated secrets
```

## 6.2 Partially trusted

The following are partially trusted:

```text
local administrator
network environment
Docker Engine
host firewall
imported media files
restored database dumps
```

## 6.3 Untrusted by default

The following must be treated as untrusted:

```text
unsigned capsules
unknown Docker images
old VPS disk images
old Docker volumes
old crontabs
old authorized_keys
old sudoers entries
old /tmp and /dev/shm content
logs copied from compromised machines
.env files from compromised machines
any user-provided shell command
```

Backups must not preserve malware. Recovery notes state that safe backups should include Postgres dumps, media/uploads, and configuration templates, but should not restore whole old disks, `/tmp`, `/dev/shm`, old crontabs, unknown systemd services, old authorized keys, old sudoers files, or unverified Docker volumes. 

---

## 7. Privilege model

## 7.1 Two-process model

The Manager must not run permanently as root/admin.

Canonical model:

```text
Konnaxion Capsule Manager
  - normal user process
  - no direct Docker socket access
  - no direct firewall control
  - no shell command execution

Konnaxion Agent
  - local service
  - privileged only where needed
  - exposes narrow local API
  - validates every operation
```

## 7.2 Agent privilege scope

The Agent may perform these privileged operations:

```text
create /opt/konnaxion directories
set file ownership and permissions
install or update systemd service files owned by Konnaxion
apply firewall rules for approved network profiles
create Docker networks
create Docker volumes
load allowlisted OCI images
run approved Docker Compose projects
read approved container logs
stop/start approved Konnaxion services
create and restore approved backups
rotate generated secrets
run Security Gate checks
```

The Agent must not allow:

```text
arbitrary shell execution
arbitrary Docker image execution
arbitrary docker-compose.yml execution
mounting host root filesystem into containers
mounting /var/run/docker.sock into application containers
privileged containers
host network mode
arbitrary port publishing
arbitrary systemd unit creation
arbitrary sudoers modification
editing SSH server configuration without explicit approved operation
```

---

## 8. User and group model

## 8.1 Canonical users

Recommended host-level users:

```text
kx-agent    system service user for Konnaxion Agent
kx-data     non-login owner for instance data
ops         optional human maintenance user
```

Legacy names such as `deploy` may exist on old VPS deployments, but the capsule architecture should avoid relying on a broad `deploy` user with Docker control.

## 8.2 Docker group rule

The Agent model must avoid placing normal users in the `docker` group.

The recovery notes warn that the previous breach involved malicious Docker containers and cron persistence. They explicitly recommend avoiding `sudo usermod -aG docker deploy`, because Docker group access effectively grants root-level power. 

Canonical rule:

```text
Normal user accounts MUST NOT be members of the docker group.
Konnaxion Capsule Manager MUST NOT access Docker directly.
Only Konnaxion Agent may control Docker, and only through allowlisted operations.
```

---

## 9. Local API model

The Agent exposes a local API to the Manager.

## 9.1 Binding

The Agent API must bind only to local interfaces:

```text
127.0.0.1
::1
Unix domain socket
```

The Agent API must never bind to:

```text
0.0.0.0
public IP
LAN IP by default
Tailscale IP by default
```

## 9.2 Authentication

Every Manager-to-Agent request must be authenticated.

Acceptable mechanisms:

```text
Unix socket with strict filesystem permissions
local token generated at install time
OS keychain-backed token
mutual local certificate pair
```

The Agent must reject unauthenticated requests.

## 9.3 Authorization

Every request must pass an operation allowlist.

Example categories:

```text
capsule.import
capsule.verify
instance.create
instance.start
instance.stop
instance.status
instance.logs
instance.backup
instance.restore
instance.update
instance.rollback
network.set_profile
security.check
secrets.rotate
```

The API must not include:

```text
shell.exec
docker.run
docker.compose.raw
firewall.raw
systemctl.raw
file.write_anywhere
```

---

## 10. Capsule verification

Before importing or running a capsule, the Agent must verify:

```text
capsule file extension is .kxcap
manifest exists
manifest schema is valid
capsule version is supported
APP_VERSION is compatible
PARAM_VERSION is compatible
signature is valid
checksums match
OCI images match manifest
profiles are valid
services are allowlisted
ports are allowlisted
volumes are allowlisted
no secrets are embedded
```

A capsule must be rejected if it attempts to:

```text
run privileged containers
mount Docker socket
use host network
publish blocked ports
mount host root directories
override Agent policies
include unknown service names
include unknown images
include real secrets
disable Security Gate
disable audit logging
```

---

## 11. Docker runtime restrictions

## 11.1 Allowed services

The Agent may only start the canonical Konnaxion service set:

```text
traefik
frontend-next
django-api
postgres
redis
celeryworker
celerybeat
flower
media-nginx
```

`flower` is allowed only when private or explicitly protected.

## 11.2 Container restrictions

All application containers must use:

```text
restart policy approved by profile
non-root user where practical
read-only filesystem where practical
explicit volumes only
explicit networks only
no privileged mode
no host network
no Docker socket mount
no broad host mounts
limited capabilities
healthcheck required
```

## 11.3 Unknown containers

The Agent must detect unknown containers attached to Konnaxion networks or using Konnaxion names.

Result:

```text
Security Gate status: FAIL_BLOCKING
Instance state: security_blocked
```

---

## 12. Network security model

## 12.1 Public entrypoint rule

Traefik is the only public entrypoint.

Canonical routing:

```text
/        -> frontend-next
/api/    -> django-api
/admin/  -> django-api
/media/  -> media-nginx
```

The existing deployment guide confirms the intended routing pattern: root to Next.js, `/api/` to Django, `/admin/` to Django admin, and `/media/` to the media service. 

## 12.2 Ports always blocked from public exposure

The Agent must never expose these ports publicly:

```text
3000  Next.js direct
5000  Django/Gunicorn internal
5432  PostgreSQL
6379  Redis
5555  Flower/dashboard
8000  Django dev server
Docker daemon TCP ports
```

The recovery guide explicitly warns that public users should reach only Traefik on `80/443`, not frontend direct on `3000`, dashboard/admin on `5555`, Postgres on `5432`, Redis on `6379`, or Django/Gunicorn on `8000`. 

## 12.3 Network profiles

The Agent may apply only canonical network profiles:

```text
local_only
intranet_private
private_tunnel
public_temporary
public_vps
offline
```

Default profile:

```env
KX_NETWORK_PROFILE=intranet_private
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

## 12.4 Public temporary mode

If public temporary mode is enabled:

```text
expiration is mandatory
auth is mandatory where supported
tunnel must close automatically
public exposure must be logged
rollback to private mode must be automatic
```

Required variables:

```env
KX_PUBLIC_MODE_ENABLED=true
KX_PUBLIC_MODE_EXPIRES_AT=<ISO8601_TIMESTAMP>
```

If `KX_PUBLIC_MODE_ENABLED=true` and `KX_PUBLIC_MODE_EXPIRES_AT` is empty, Security Gate must return:

```text
FAIL_BLOCKING
```

---

## 13. Firewall control

The Agent may manage firewall rules only through approved profiles.

## 13.1 Deny-by-default baseline

```text
deny incoming
allow outgoing
allow local loopback
allow approved profile ports only
```

## 13.2 Approved exposure by profile

| Profile            | Allowed exposure                  |
| ------------------ | --------------------------------- |
| `offline`          | no external exposure              |
| `local_only`       | localhost only                    |
| `intranet_private` | LAN `443`, optional `80` redirect |
| `private_tunnel`   | tunnel/VPN only                   |
| `public_temporary` | temporary tunnel endpoint         |
| `public_vps`       | `80/443`, SSH restricted          |

## 13.3 SSH policy

The Agent should not expose SSH automatically for appliance/demo modes.

If SSH is enabled:

```text
key-only
no root login
no password login
restricted source IP or VPN
```

---

## 14. Secrets model

## 14.1 Capsule secrets rule

Capsules must not contain real secrets.

Forbidden inside `.kxcap`:

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
DATABASE_URL with password
SSH private keys
API tokens
provider credentials
Django admin password
Sentry DSN if private
email provider password
storage provider secret
```

The deployment/security notes identify these as sensitive values that must not be pasted into logs/chats and must be rotated if exposed. 

## 14.2 Secret generation

The Agent generates secrets on install:

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
initial admin password or one-time setup token
internal service tokens
local Manager-Agent token
backup encryption key if enabled
```

## 14.3 Secret storage

Secrets must be stored under the instance environment directory:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/env/
```

Required permissions:

```text
owner: kx-agent or root
group: kx-agent
mode: 0600 for secret files
mode: 0700 for env directory
```

## 14.4 Secret rotation

The Agent must support:

```text
kx instance rotate-secrets <INSTANCE_ID>
```

At minimum, rotation must cover:

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
Manager-Agent local token
initial admin setup token
```

Rotation must trigger:

```text
backup before rotation
service restart
healthcheck
audit event
```

---

## 15. File system model

## 15.1 Canonical paths

```text
/opt/konnaxion/
├── capsules/
├── instances/
├── shared/
├── releases/
├── manager/
└── backups/
```

Instance path:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/
├── env/
├── postgres/
├── redis/
├── media/
├── logs/
├── backups/
└── state/
```

## 15.2 Path restrictions

The Agent may write only under:

```text
/opt/konnaxion
/etc/systemd/system/konnaxion-agent.service
approved firewall configuration locations
approved log directory
```

The Agent must not write arbitrary files under:

```text
/etc/sudoers.d
/root
/home/*
/tmp for persistent scripts
/dev/shm
/usr/bin
/usr/local/bin except approved installed binaries
```

## 15.3 Temporary files

Temporary files must be:

```text
created under Agent-owned temp directory
not executable by default
removed after operation
never used as persistence
```

---

## 16. Security Gate integration

Before starting or updating an instance, the Agent must run Security Gate.

## 16.1 Required checks

```text
capsule_signature
image_checksums
manifest_schema
secrets_present
secrets_not_default
firewall_enabled
dangerous_ports_blocked
postgres_not_public
redis_not_public
docker_socket_not_mounted
no_privileged_containers
no_host_network
allowed_images_only
admin_surface_private
backup_configured
unknown_containers_absent
unknown_cron_absent
suspicious_tmp_absent
unexpected_sudoers_absent
```

## 16.2 Status values

The Agent must return only canonical Security Gate statuses:

```text
PASS
WARN
FAIL_BLOCKING
SKIPPED
UNKNOWN
```

## 16.3 Blocking conditions

The following always return `FAIL_BLOCKING`:

```text
unsigned capsule
invalid checksum
unknown image
privileged container
Docker socket mounted
host network mode
public Postgres
public Redis
public Docker daemon
public frontend direct port
public Flower/dashboard without protection
missing generated secrets
default passwords
unknown Konnaxion-like containers
known malware indicators
```

Known malware indicators include names or patterns from the previous incident:

```text
amco_*
negoroo/amco
supportxmr
rx/0
/tmp/sshd
pakchoi
/dev/shm executable files
unexpected crontabs
unexpected sudoers files
```

The incident recovery notes specifically instruct checking for these indicators after deployment and during cleanup.

---

## 17. Audit logging

The Agent must log every privileged action.

## 17.1 Audit event fields

```yaml
event_id: string
timestamp: ISO8601
instance_id: string
actor: local_user | manager | system
operation: string
request_id: string
result: PASS | WARN | FAIL | DENIED
network_profile: string
exposure_mode: string
capsule_id: string
capsule_version: string
details_redacted: object
```

## 17.2 Never log

Audit logs must never include:

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
DATABASE_URL with password
API keys
tokens
private keys
admin passwords
backup encryption keys
```

## 17.3 Required logged actions

```text
capsule import
capsule verification
instance create
instance start
instance stop
instance update
instance rollback
network profile change
public temporary mode enable
public temporary mode expire
secret generation
secret rotation
backup
backup verification
backup test-restore
restore
pre-restore backup
pre-update backup
Security Gate failure
unknown container detection
firewall rule application
```

---

## 18. Backup, restore and rollback security

This section defines the Agent-side security rules for backup, restore and rollback. The detailed backup format, retention policy and operator workflows are defined in `DOC-09_Konnaxion_Backup_Restore_Rollback.md`.

The Agent must treat backup/restore as privileged security-sensitive operations, not as simple file copy operations.

## 18.1 Approved backup operations

The Agent may perform only these backup operations:

```text
create verified backup sets
create pre-update backups
create pre-restore backups
create manual backups
list backups for a known Konnaxion Instance
verify backup manifests and checksums
test-restore a backup into a temporary local_only instance
export a backup only through an approved backup/export path
expire backups according to canonical retention policy
quarantine failed or suspicious backups
```

The Agent must not allow raw filesystem backup jobs requested by the UI or capsule.

## 18.2 Approved backup contents

Approved backup contents:

```text
PostgreSQL logical dump
media/uploads archive
instance metadata
capsule reference metadata
network profile snapshot
Security Gate report
healthcheck result
safe configuration templates
redacted manifest copy
checksums
backup manifest
```

The backup protects **application data**, not the host operating system.

## 18.3 Backup exclusions

Backups must exclude:

```text
host system files
entire disk images
Docker daemon state
Docker socket
old crontabs
old systemd services
/tmp
/dev/shm
authorized_keys
sudoers files
unknown Docker volumes
malware scan positives
private keys
plaintext secrets
raw .env files containing secrets
```

If any excluded content is detected in a backup plan or backup set, the Agent must return:

```text
FAIL_BLOCKING
```

and refuse to promote the backup to verified status.

## 18.4 Approved restore operations

The Agent may perform only these restore operations:

```text
restore PostgreSQL from a verified dump
restore media/uploads from a verified archive
restore into a new Konnaxion Instance
restore into an existing Konnaxion Instance after pre-restore backup
restore database-only
restore media-only
run migrations after restore when required
run Security Gate after restore
run healthchecks after restore
```

Preferred restore target for risky operations:

```text
new instance + local_only profile
```

This avoids overwriting a working instance before the restored state is verified.

## 18.5 Forbidden restore operations

The Agent must never restore:

```text
old disk image
old Docker daemon state
old system users
old crontabs
old sudoers files
old authorized_keys
old /tmp
old /dev/shm
unknown containers
unknown Docker volumes
unverified binaries
unverified systemd units
malware cleanup quarantine folders
```

The Agent must restore only approved Konnaxion application state:

```text
database
media
metadata
safe generated configuration
```

## 18.6 Restore policy

Before restore, the Agent must:

```text
verify backup metadata
verify backup checksums
scan for forbidden paths
scan for leaked secrets
verify target instance state
create a pre-restore backup unless impossible
stop affected services
restore approved data only
run migrations if required
run Security Gate
restart services
run healthcheck
log the operation
```

A restore is successful only if:

```text
backup verification passes
restore operation completes
Security Gate returns PASS or allowed WARN
healthcheck passes
dangerous ports remain blocked
Postgres remains internal
Redis remains internal
Docker socket remains unmounted
```

## 18.7 Backup and restore API boundary

The Manager may request high-level operations such as:

```text
backup this instance
verify this backup
restore this backup
restore this backup into a new instance
rollback this instance
```

The Manager must not request low-level operations such as:

```text
dump arbitrary path
restore arbitrary path
run arbitrary pg_restore command
write arbitrary file
execute arbitrary shell script
mount arbitrary Docker volume
```

The Agent owns the implementation details and must enforce the policy regardless of UI behavior.

---

## 19. Update and rollback security

## 19.1 Immutable capsule rule

Capsules are immutable after import.

Updates use a new capsule:

```text
current -> konnaxion-v14-demo-2026.04.30
next    -> konnaxion-v14-demo-2026.05.05
```

The Agent must never patch an imported `.kxcap` in place.

## 19.2 Approved rollback operations

The Agent may perform only these rollback operations:

```text
capsule rollback
data rollback from verified backup
full instance rollback from verified backup and previous capsule reference
automatic rollback after failed update
manual rollback requested by Manager
```

Default rule:

```text
capsule rollback first
data rollback only when schema/data changes require it
```

The Agent must not automatically roll back data unless the update process marked the database or media as changed.

## 19.3 Update sequence

Canonical update sequence:

```text
1. Verify new capsule signature.
2. Verify new capsule checksums.
3. Create pre-update backup.
4. Load only allowlisted images.
5. Create staged runtime.
6. Run migrations if required.
7. Run healthchecks.
8. Run Security Gate.
9. Switch current capsule pointer only after validation.
10. Stop old runtime.
11. Log update result.
```

If validation fails before the capsule pointer switch, the Agent must discard the staged runtime and keep the current instance unchanged.

## 19.4 Rollback sequence

Canonical rollback sequence:

```text
1. Stop failed runtime.
2. Restore previous capsule pointer.
3. Restore compatible DB backup only if required.
4. Restore media only if required.
5. Start previous runtime.
6. Run migrations only if compatible and required.
7. Run healthchecks.
8. Run Security Gate.
9. Log rollback result.
```

If rollback fails, the Agent must:

```text
disable public exposure
switch to safest private profile available
mark instance security_blocked or failed
keep services stopped if integrity is unknown
preserve logs and rollback metadata
```

---

## 20. Agent API — canonical operations

The Agent API must expose only high-level operations.

```text
GET  /v1/status
GET  /v1/instances
GET  /v1/instances/<INSTANCE_ID>

POST /v1/capsules/import
POST /v1/capsules/verify

POST /v1/instances/create
POST /v1/instances/<INSTANCE_ID>/start
POST /v1/instances/<INSTANCE_ID>/stop
POST /v1/instances/<INSTANCE_ID>/restart
POST /v1/instances/<INSTANCE_ID>/update
POST /v1/instances/<INSTANCE_ID>/rollback
POST /v1/instances/<INSTANCE_ID>/network-profile
POST /v1/instances/<INSTANCE_ID>/security-check
POST /v1/instances/<INSTANCE_ID>/rotate-secrets

POST /v1/instances/<INSTANCE_ID>/backup
GET  /v1/instances/<INSTANCE_ID>/backups
POST /v1/instances/<INSTANCE_ID>/restore
POST /v1/instances/restore-new
POST /v1/backups/<BACKUP_ID>/verify
POST /v1/backups/<BACKUP_ID>/test-restore

GET  /v1/instances/<INSTANCE_ID>/logs
GET  /v1/instances/<INSTANCE_ID>/health
```

These endpoints are logical API operations. They do not imply public HTTP exposure. The Agent API must remain local-only.

Forbidden API patterns:

```text
POST /shell
POST /exec
POST /docker/run
POST /docker/raw
POST /firewall/raw
POST /systemctl/raw
POST /files/write
POST /files/read-arbitrary
POST /backup/raw-path
POST /restore/raw-path
POST /postgres/raw
```

The Agent must not expose raw Docker, raw firewall, raw systemd, raw file, raw PostgreSQL, or shell execution primitives.

---

## 21. Runtime health checks

The Agent must verify:

```text
Traefik responds on approved entrypoint
frontend-next responds behind Traefik
django-api responds behind Traefik
/api/ health endpoint responds
/admin/ is reachable only through approved route
Postgres reachable only from internal network
Redis reachable only from internal network
Celery worker is running
Celery beat is running if enabled
media-nginx serves expected media route
no blocked ports are externally reachable
```

The frontend runbook confirms that the current Next.js service runs on port `3000` locally and must be validated through both local service checks and public domain checks; in the capsule model, this direct port must remain internal behind Traefik. 

---

## 22. Failure behavior

## 22.1 Fail closed

If the Agent cannot determine whether a configuration is safe, it must fail closed.

Examples:

```text
firewall status unknown -> FAIL_BLOCKING
capsule signature unknown -> FAIL_BLOCKING
Docker socket mount unknown -> FAIL_BLOCKING
public port state unknown -> FAIL_BLOCKING
```

## 22.2 Degraded mode

The Agent may allow `degraded` state only when:

```text
network remains private
data remains safe
no dangerous port is exposed
no unknown container is running
failure is recoverable
```

## 22.3 Security blocked state

When a blocking security issue exists:

```text
KX_INSTANCE_STATE=security_blocked
```

The Manager must display:

```text
Instance blocked by Security Gate.
No public exposure has been enabled.
Review security check details.
```

---

## 23. Configuration variables

Agent-specific variables use the `KX_` prefix.

```env
KX_AGENT_ENABLED=true
KX_AGENT_BIND=unix:///run/konnaxion-agent.sock
KX_AGENT_LOG_LEVEL=INFO
KX_AGENT_AUDIT_LOG=/opt/konnaxion/manager/logs/audit.log

KX_REQUIRE_SIGNED_CAPSULE=true
KX_ALLOW_UNKNOWN_IMAGES=false
KX_ALLOW_PRIVILEGED_CONTAINERS=false
KX_ALLOW_DOCKER_SOCKET_MOUNT=false
KX_ALLOW_HOST_NETWORK=false

KX_DEFAULT_NETWORK_PROFILE=intranet_private
KX_PUBLIC_MODE_ENABLED=false
KX_PUBLIC_MODE_EXPIRES_AT=

KX_BACKUP_ENABLED=true
KX_BACKUP_RETENTION_DAYS=14
KX_SECURITY_GATE_REQUIRED=true
```

---

## 24. Minimal systemd unit concept

The production implementation may use a system service similar to:

```ini
[Unit]
Description=Konnaxion Agent
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
ExecStart=/opt/konnaxion/manager/bin/konnaxion-agent
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/opt/konnaxion /run /var/log/konnaxion
EnvironmentFile=-/opt/konnaxion/manager/agent.env

[Install]
WantedBy=multi-user.target
```

The final unit must be reviewed before production. If rootless Docker is adopted, the service user and permissions should be reduced accordingly.

---

## 25. Acceptance criteria

The Agent security model is implemented correctly when:

```text
Manager cannot run Docker directly.
Manager cannot execute arbitrary shell commands.
Agent API is local-only.
Agent rejects unsigned capsules.
Agent rejects unknown images.
Agent rejects dangerous ports.
Agent rejects privileged containers.
Agent rejects Docker socket mounts.
Agent rejects host network mode.
Agent generates secrets locally.
Agent never stores real secrets inside .kxcap.
Agent applies deny-by-default network profile.
Agent defaults to intranet_private or local_only.
Agent requires expiration for public_temporary.
Agent blocks startup if Security Gate fails.
Agent logs all privileged operations.
Agent supports backup before update.
Agent supports pre-restore backup before destructive restore.
Agent verifies backups before restore.
Agent rejects backups containing forbidden paths or leaked secrets.
Agent supports restore into a new local_only instance.
Agent supports rollback after failed update.
Agent disables public exposure when rollback fails.
Agent detects known compromise indicators.
```

---

## 26. Implementation priority

### Phase 1 — Minimum secure Agent

```text
local-only API
capsule signature verification
manifest validation
secret generation
Docker Compose allowlist
network profile enforcement
dangerous port blocking
Security Gate basic checks
audit log
start/stop/status
```

### Phase 2 — Appliance-grade Agent

```text
firewall profile automation
backup/restore
update/rollback
public temporary mode expiration
unknown container detection
suspicious persistence checks
Manager UI integration
local token rotation
```

### Phase 3 — Hardened enterprise/demo box

```text
rootless Docker evaluation
signed Agent updates
backup encryption
remote health reporting
policy export
tamper detection
hardware appliance image
```

---

## 27. Final rule

The Konnaxion Agent exists to make Konnaxion plug-and-play **without making it unsafe**.

The Agent must make the secure path the default path:

```text
private by default
minimal configuration
no dangerous ports
no arbitrary Docker control
no embedded secrets
signed capsules only
Security Gate before runtime
automatic rollback where possible
```

If a configuration is convenient but unsafe, the Agent must reject it.

