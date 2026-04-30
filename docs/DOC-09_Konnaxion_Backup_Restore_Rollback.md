---
doc_id: DOC-09
title: Konnaxion Backup, Restore & Rollback
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
  - DOC-05_Konnaxion_Agent_Security_Model.md
  - DOC-06_Konnaxion_Network_Profiles.md
  - DOC-07_Konnaxion_Security_Gate.md
  - DOC-08_Konnaxion_Runtime_Docker_Compose.md
related_docs:
  - DOC-11_Konnaxion_Box_Appliance_Image.md
  - DOC-12_Konnaxion_Install_Runbook.md
  - DOC-14_Konnaxion_Operator_Guide.md
---

# DOC-09 — Konnaxion Backup, Restore & Rollback

## 1. Purpose

This document defines the canonical backup, restore and rollback model for **Konnaxion Capsule Manager**, **Konnaxion Agent**, **Konnaxion Instance** and **Konnaxion Box**.

The goal is to make recovery safe, repeatable and plug-and-play while preserving the core security principle:

```text
Never preserve malware.
Never restore unverified system state.
Never mix capsule code with instance data.
```

This document is written for the target architecture:

```text
Konnaxion Capsule
  = immutable application package

Konnaxion Instance
  = data, secrets, media, logs, backups and runtime state
```

Backup, restore and rollback are not generic file copy operations. They are controlled lifecycle operations executed by **Konnaxion Agent** and presented through **Konnaxion Capsule Manager**.

---

## 2. Scope

This document covers:

```text
PostgreSQL backups
media/uploads backups
instance configuration backups
secret backup policy
capsule rollback
instance rollback
database restore
media restore
restore into new instance
health validation after restore
automatic rollback after failed update
backup retention
backup verification
disaster recovery
```

This document does **not** cover:

```text
full disk cloning
forensic imaging
provider-level snapshot implementation details
CI/CD build pipeline internals
external database provider backups
manual incident response beyond restore safety
arbitrary host migration
arbitrary Docker volume migration
```

---

## 3. Canonical Terms

| Term | Meaning |
|---|---|
| `Konnaxion Capsule` | Signed `.kxcap` file containing application images, manifest, profiles and templates. |
| `Konnaxion Instance` | Installed runtime state: database, media, logs, secrets and backups. |
| `Konnaxion Capsule Manager` | User-facing app that imports capsules, starts/stops instances and manages network mode. |
| `Konnaxion Agent` | Local privileged service that performs controlled system actions. |
| `Konnaxion Box` | Dedicated plug-and-play host machine. |
| `Backup Set` | One complete backup unit with manifest, database dump, media archive, metadata and checksums. |
| `Restore Plan` | The validated procedure generated before applying a restore. |
| `Rollback` | Returning to the previous known-good capsule, database snapshot or instance state. |
| `Preflight` | Safety validation before backup, restore or rollback. |
| `Postflight` | Health validation after backup, restore or rollback. |

---

## 4. Canonical Paths

All new documentation must use these target paths.

```text
/opt/konnaxion/
├── capsules/
├── instances/
├── manager/
├── agent/
├── shared/
├── releases/
└── backups/
```

Instance layout:

```text
/opt/konnaxion/instances/<KX_INSTANCE_ID>/
├── env/
├── postgres/
├── redis/
├── media/
├── logs/
├── backups/
└── state/
```

Canonical backup storage:

```text
/opt/konnaxion/backups/
└── <KX_INSTANCE_ID>/
    ├── daily/
    ├── weekly/
    ├── monthly/
    ├── pre-update/
    ├── pre-restore/
    └── manual/
```

Canonical example:

```text
/opt/konnaxion/backups/demo-001/daily/20260430_230000/
```

### 4.1 Global Backup Path vs Instance Backup Path

The canonical backup repository is:

```text
/opt/konnaxion/backups/<KX_INSTANCE_ID>/
```

The instance-local backup directory is reserved for local pointers, state, restore markers or temporary Agent work files:

```text
/opt/konnaxion/instances/<KX_INSTANCE_ID>/backups/
```

Rules:

```text
Do store durable backup sets under /opt/konnaxion/backups/<KX_INSTANCE_ID>/.
Do not treat /opt/konnaxion/instances/<KX_INSTANCE_ID>/backups/ as the durable backup repository.
Do not duplicate large backup archives in both paths unless an explicit cache policy exists.
```

---

## 5. Backup Policy

### 5.1 Backup Classes

Konnaxion defines six canonical backup classes.

| Class | Trigger | Purpose |
|---|---|---|
| `daily` | Automatic schedule | Routine recovery point |
| `weekly` | Automatic schedule | Longer retention recovery point |
| `monthly` | Automatic schedule | Archive-grade recovery point |
| `pre-update` | Before capsule update | Rollback before applying new capsule |
| `pre-restore` | Before restore | Safety backup before overwriting current state |
| `manual` | User action | Operator-controlled snapshot |

The Konnaxion Agent must expose backup creation through the canonical CLI and Manager UI:

```bash
kx instance backup <KX_INSTANCE_ID> --class daily
kx instance backup <KX_INSTANCE_ID> --class pre-update
kx instance backup <KX_INSTANCE_ID> --class manual
```

### 5.2 Backup Variables

The following variables are canonical for DOC-09 and should be mirrored in `DOC-00_Konnaxion_Canonical_Variables.md`.

```env
KX_BACKUP_ENABLED=true
KX_BACKUP_ROOT=/opt/konnaxion/backups
KX_BACKUP_RETENTION_DAYS=14
KX_DAILY_BACKUP_RETENTION_DAYS=14
KX_WEEKLY_BACKUP_RETENTION_WEEKS=8
KX_MONTHLY_BACKUP_RETENTION_MONTHS=12
KX_PRE_UPDATE_BACKUP_RETENTION_COUNT=5
KX_PRE_RESTORE_BACKUP_RETENTION_COUNT=5
```

Internal Agent variables used in implementation examples:

```env
KX_COMPOSE_FILE=<GENERATED_BY_AGENT>
KX_BACKUP_DIR=<GENERATED_BY_AGENT>
KX_HOST=<GENERATED_FROM_NETWORK_PROFILE>
```

These internal variables are not intended for manual operator configuration.

### 5.3 Default Retention

Default retention:

```text
daily backups:       14 days
weekly backups:      8 weeks
monthly backups:     12 months
pre-update backups:  last 5
pre-restore backups: last 5
```

For demo-only deployments, the Manager may reduce retention, but it must never disable backups silently.

### 5.4 Default Schedule

Canonical automatic schedule:

```text
daily backup:   03:00 local time
weekly backup:  Sunday 03:30 local time
monthly backup: first day of month 04:00 local time
```

For offline/intranet environments, schedule must not depend on external services.

---

## 6. What Must Be Backed Up

A Konnaxion backup set must include:

```text
PostgreSQL logical dump
media/uploads directory
instance manifest snapshot
network profile snapshot
capsule reference
environment template reference
redacted environment metadata
backup manifest
checksums
healthcheck result
Manager/Agent version metadata
```

### 6.1 PostgreSQL

Canonical database backup format:

```text
logical dump
compressed or externally compressed
checksummed
restorable into a clean Postgres volume
```

Preferred command pattern inside the controlled Agent:

```bash
docker compose -f "$KX_COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --format=custom \
  --no-owner \
  --no-acl \
  > "$KX_BACKUP_DIR/postgres.dump"
```

The custom format is preferred because it supports stronger restore workflows with `pg_restore`.

### 6.2 Media

Media files must be backed up separately from the database.

Canonical path:

```text
/opt/konnaxion/instances/<KX_INSTANCE_ID>/media/
```

Backup target:

```text
<BACKUP_SET>/media.tar.zst
```

Preferred command pattern:

```bash
tar -C "/opt/konnaxion/instances/$KX_INSTANCE_ID" \
  -cf - media \
  | zstd -T0 -o "$KX_BACKUP_DIR/media.tar.zst"
```

### 6.3 Instance Metadata

Each backup must include:

```text
instance.json
capsule.json
network-profile.json
security-gate.json
healthcheck.json
versions.json
```

These files are used to verify compatibility before restore.

### 6.4 Environment Metadata

The backup may include **redacted** environment metadata.

Allowed:

```text
variable names
whether required values exist
hashes/fingerprints of values
profile-derived hostnames
non-secret feature flags
```

Forbidden:

```text
DJANGO_SECRET_KEY plaintext
POSTGRES_PASSWORD plaintext
DATABASE_URL plaintext
API keys
tokens
private keys
SSH keys
full .env files with secrets
```

---

## 7. What Must Never Be Backed Up For Normal Restore

Normal Konnaxion backups must not include:

```text
entire disk images
/tmp
/dev/shm
system crontabs
user crontabs
unknown systemd services
old authorized_keys
old sudoers files
unknown Docker volumes
Docker daemon state
Docker socket
unverified binaries
malware cleanup quarantine folders
provider-level snapshots from compromised hosts
```

This rule exists because a compromised host can contain persistence outside the application directory. Konnaxion restore must recover the application and data, not the attacker’s persistence.

---

## 8. Backup Set Structure

Each backup set must use this structure:

```text
<BACKUP_SET>/
├── backup-manifest.yaml
├── postgres.dump
├── media.tar.zst
├── instance.json
├── capsule.json
├── network-profile.json
├── security-gate.json
├── healthcheck-before.json
├── checksums.sha256
├── restore-plan.template.yaml
└── logs/
    ├── backup.log
    └── verification.log
```

Example:

```text
/opt/konnaxion/backups/demo-001/daily/20260430_230000/
├── backup-manifest.yaml
├── postgres.dump
├── media.tar.zst
├── instance.json
├── capsule.json
├── network-profile.json
├── security-gate.json
├── healthcheck-before.json
├── checksums.sha256
└── logs/
```

---

## 9. Backup Manifest Schema

Canonical `backup-manifest.yaml`:

```yaml
schema_version: kx-backup-manifest-v1
backup_id: demo-001_20260430_230000_daily
created_at: "2026-04-30T23:00:00-04:00"
backup_class: daily

instance:
  kx_instance_id: demo-001
  kx_app_version: v14
  kx_capsule_id: konnaxion-v14-demo-2026.04.30
  kx_capsule_version: 2026.04.30-demo.1
  kx_param_version: kx-param-2026.04.30

environment:
  kx_network_profile: intranet_private
  kx_exposure_mode: private
  public_mode_enabled: false

contents:
  postgres_dump: postgres.dump
  media_archive: media.tar.zst
  instance_metadata: instance.json
  capsule_metadata: capsule.json
  network_profile: network-profile.json
  security_gate: security-gate.json

database:
  engine: postgres
  dump_format: custom
  logical_backup: true

security:
  secrets_included: false
  full_disk_backup: false
  contains_tmp: false
  contains_crontabs: false
  contains_authorized_keys: false
  contains_sudoers: false
  contains_docker_socket: false

verification:
  checksum_file: checksums.sha256
  backup_verified: true
  restore_tested: false

notes: ""
```

---

## 10. Backup Preflight

Before any backup, the Konnaxion Agent must run:

```bash
kx security check <KX_INSTANCE_ID>
kx instance status <KX_INSTANCE_ID>
```

The Agent also runs an internal backup preflight operation. This operation may be logged as:

```text
backup_preflight
```

It should not be required as a public operator command.

Preflight checks:

```text
instance exists
instance state is running or stopped
Docker services are known
Postgres service is reachable
media path exists
backup target is writable
available disk space is sufficient
capsule reference exists
network profile is known
Security Gate is not FAIL_BLOCKING
no unknown containers are attached to Konnaxion network
no forbidden paths are included in backup plan
```

If preflight fails, the backup must return:

```text
FAIL_BLOCKING
```

and no partial backup should be promoted to a valid backup set.

---

## 11. Backup Postflight

After backup, the Agent must verify:

```text
postgres.dump exists
media archive exists or is explicitly empty
manifest exists
checksums file exists
checksums match
backup size is non-zero unless instance is empty
backup log contains no secrets
backup set is marked verified
```

Postflight status values:

```text
PASS
WARN
FAIL_BLOCKING
```

A backup set is valid only when:

```text
backup-manifest.yaml exists
checksums.sha256 exists
verification.backup_verified=true
postflight status is PASS
```

---

## 12. Restore Policy

Restore must be deliberate, reversible and validated.

Before any restore, the Manager must:

```text
show the source backup
show the target instance
show what will be overwritten
create a pre-restore backup of current state
run restore preflight
require explicit confirmation
stop affected services
restore database and media
run migrations if needed
run Security Gate
run healthchecks
restart services
```

The Manager must not restore directly over an instance without first creating a `pre-restore` backup, unless the instance is already marked `failed` and no recoverable state exists.

---

## 13. Restore Types

### 13.1 Full Instance Restore

Restores:

```text
PostgreSQL
media/uploads
instance metadata
network profile
capsule reference if compatible
```

Command:

```bash
kx instance restore <KX_INSTANCE_ID> \
  --from <BACKUP_ID> \
  --mode full
```

### 13.2 Database-Only Restore

Restores:

```text
PostgreSQL only
```

Command:

```bash
kx instance restore <KX_INSTANCE_ID> \
  --from <BACKUP_ID> \
  --mode database-only
```

### 13.3 Media-Only Restore

Restores:

```text
media/uploads only
```

Command:

```bash
kx instance restore <KX_INSTANCE_ID> \
  --from <BACKUP_ID> \
  --mode media-only
```

### 13.4 Restore Into New Instance

Preferred for high-risk recovery:

```bash
kx instance restore-new \
  --from <BACKUP_ID> \
  --new-instance-id demo-restore-001 \
  --network local_only
```

This is the safest method because it preserves the original instance and allows validation before switch-over.

---

## 14. Restore Preflight

Restore preflight must verify:

```text
backup manifest exists
backup checksums match
backup was verified
backup does not include forbidden paths
target instance exists or new target path is clean
target has enough disk space
target capsule compatibility is acceptable
target profile is allowed
Postgres service can be recreated
media path can be restored
Security Gate policy can be enforced
```

Compatibility rules:

```text
same APP_VERSION: allowed
newer patch capsule: allowed after migration plan
older capsule: warn or block depending on migration history
different PARAM_VERSION: require compatibility check
different schema major version: block unless migration adapter exists
```

### 14.1 Restore Network Profile Rules

Restore must be private by default.

```text
Restore into local_only:
  safest default for validation and test restore

Restore into intranet_private:
  allowed after Security Gate PASS

Restore into private_tunnel:
  allowed only after tunnel configuration validation

Restore into public_temporary:
  must not automatically enable public exposure
  requires new explicit temporary access request

Restore into public_vps:
  requires explicit approval, firewall PASS and public_vps policy PASS
```

A backup restore must not silently re-enable public exposure, even if the source backup was created while public mode was active.

---

## 15. Restore Procedure — Existing Instance

Canonical sequence:

```text
1. Set instance state to restoring.
2. Create pre-restore backup.
3. Stop frontend-next, django-api, celeryworker, celerybeat.
4. Keep postgres available for dump or stop/recreate depending on restore mode.
5. Verify backup checksums.
6. Restore database.
7. Restore media.
8. Run migrations.
9. Run collectstatic if required.
10. Run Security Gate.
11. Start services.
12. Run healthchecks.
13. Mark instance running if checks pass.
14. Mark instance degraded or failed if checks fail.
```

Operator command pattern:

```bash
kx instance backup <KX_INSTANCE_ID> --class pre-restore

kx instance restore <KX_INSTANCE_ID> \
  --from <BACKUP_ID> \
  --mode full

kx security check <KX_INSTANCE_ID>
kx instance health <KX_INSTANCE_ID>
```

Stopping individual services is an internal Agent operation, not a normal operator command.

---

## 16. PostgreSQL Restore Procedure

For a full database restore, the Agent should use a clean database target.

Canonical pattern:

```bash
docker compose -f "$KX_COMPOSE_FILE" exec -T postgres \
  dropdb -U "$POSTGRES_USER" "$POSTGRES_DB"

docker compose -f "$KX_COMPOSE_FILE" exec -T postgres \
  createdb -U "$POSTGRES_USER" "$POSTGRES_DB"

cat "$KX_BACKUP_DIR/postgres.dump" | docker compose -f "$KX_COMPOSE_FILE" exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --no-owner \
  --no-acl \
  --clean \
  --if-exists
```

If the restore is into a brand-new Postgres volume, `--clean --if-exists` may be omitted.

After restore:

```bash
docker compose -f "$KX_COMPOSE_FILE" run --rm django-api \
  python manage.py migrate

docker compose -f "$KX_COMPOSE_FILE" run --rm django-api \
  python manage.py check --deploy
```

If the implementation-specific Compose service name differs from `django-api`, the Agent must map it internally. Documentation must continue to use the canonical service name `django-api`.

---

## 17. Media Restore Procedure

Media restore must not blindly merge unknown files into the existing media directory.

Preferred pattern:

```text
1. Move current media to media.previous.<timestamp>.
2. Extract media archive into a new clean media directory.
3. Set correct ownership and permissions.
4. Verify expected paths.
5. Keep previous media until postflight passes.
```

Command pattern:

```bash
INSTANCE_DIR="/opt/konnaxion/instances/$KX_INSTANCE_ID"
TS="$(date +%Y%m%d_%H%M%S)"

mv "$INSTANCE_DIR/media" "$INSTANCE_DIR/media.previous.$TS"
mkdir -p "$INSTANCE_DIR/media"

zstd -dc "$KX_BACKUP_DIR/media.tar.zst" \
  | tar -C "$INSTANCE_DIR" -xf -
```

Permission repair is an internal Agent operation. It may be logged as:

```text
fix_permissions
```

It should not be required as a public operator command.

If postflight fails, restore the previous media directory:

```bash
rm -rf "$INSTANCE_DIR/media"
mv "$INSTANCE_DIR/media.previous.$TS" "$INSTANCE_DIR/media"
```

---

## 18. Rollback Policy

Rollback has three levels:

| Level | Name | What changes |
|---|---|---|
| 1 | Capsule rollback | Repoints instance to previous capsule/release |
| 2 | Data rollback | Restores database/media backup |
| 3 | Full instance rollback | Restores capsule reference + database + media |

Default rollback after failed update:

```text
capsule rollback first
data rollback only if migrations or data writes changed state
```

The Manager must not automatically roll back data unless the update process marked the database as changed.

---

## 19. Capsule Rollback

Capsule rollback returns to the previous known-good `.kxcap`.

Canonical release links:

```text
/opt/konnaxion/instances/<KX_INSTANCE_ID>/state/current-capsule
/opt/konnaxion/instances/<KX_INSTANCE_ID>/state/previous-capsule
```

Command:

```bash
kx instance rollback <KX_INSTANCE_ID> --level capsule
```

Procedure:

```text
1. Stop application services.
2. Repoint current-capsule to previous-capsule.
3. Recreate containers from previous capsule.
4. Do not modify database unless required.
5. Run Security Gate.
6. Run healthchecks.
7. Mark running or degraded.
```

---

## 20. Data Rollback

Data rollback restores a backup set.

Command:

```bash
kx instance rollback <KX_INSTANCE_ID> \
  --level data \
  --from <BACKUP_ID>
```

Procedure:

```text
1. Create pre-rollback backup.
2. Stop write-capable services.
3. Restore database.
4. Restore media if included.
5. Run migrations only if required by selected capsule.
6. Run Security Gate.
7. Run healthchecks.
```

---

## 21. Full Instance Rollback

Full rollback combines capsule rollback and data rollback.

Command:

```bash
kx instance rollback <KX_INSTANCE_ID> \
  --level full \
  --from <BACKUP_ID>
```

Use this only when:

```text
capsule update failed
database migration changed schema/data
media changed during failed update
simple capsule rollback did not recover the instance
```

---

## 22. Update With Automatic Rollback

Every capsule update must follow this safe sequence:

```text
1. Verify new capsule signature.
2. Create pre-update backup.
3. Stop write-heavy services if needed.
4. Apply new capsule.
5. Start services.
6. Run migrations.
7. Run Security Gate.
8. Run healthchecks.
9. If PASS, mark new capsule current.
10. If FAIL_BLOCKING, rollback to previous capsule.
11. If database changed, request or execute data rollback according to policy.
```

Canonical command:

```bash
kx instance update <KX_INSTANCE_ID> \
  --capsule konnaxion-v14-demo-2026.05.01.kxcap \
  --auto-rollback true
```

---

## 23. Healthchecks After Restore or Rollback

Post-restore healthchecks:

```text
Traefik responds
frontend route responds
/api/ responds
/admin/ responds
/media/ responds if media exists
Django migrate state is clean
Django check passes
Celery worker is running
Celery beat is running if enabled
Redis is reachable only internally
Postgres is reachable only internally
dangerous ports are not public
```

Command pattern:

```bash
kx instance health <KX_INSTANCE_ID>
kx security check <KX_INSTANCE_ID>
```

Minimum HTTP checks:

```bash
curl -I https://<KX_HOST>/
curl -I https://<KX_HOST>/api/
curl -I https://<KX_HOST>/admin/
```

For local/intranet mode, `<KX_HOST>` may be:

```text
localhost
konnaxion.local
konnaxion.lan
private tailnet hostname
```

---

## 24. Security Gate Requirements

Backup, restore and rollback must integrate with Security Gate.

Required blocking checks:

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
```

If any critical check returns `FAIL_BLOCKING`, the Manager must not mark the restore as successful.

---

## 25. Backup Verification

Backups are not valid until verified.

Verification steps:

```text
checksum verification
manifest validation
postgres dump header check
media archive listing check
forbidden path check
secret leak scan
minimum size sanity check
optional restore-test into temporary instance
```

Command:

```bash
kx backup verify <BACKUP_ID>
```

Optional restore test:

```bash
kx backup test-restore <BACKUP_ID> \
  --temporary-instance restore-test-$(date +%Y%m%d_%H%M%S) \
  --network local_only \
  --destroy-after-pass
```

---

## 26. Secret Leak Scan

Backup verification must scan for high-risk patterns.

Block backup promotion if plaintext matches likely secrets:

```text
DJANGO_SECRET_KEY=
POSTGRES_PASSWORD=
DATABASE_URL=
PRIVATE KEY
BEGIN OPENSSH PRIVATE KEY
AWS_SECRET_ACCESS_KEY
API_KEY=
TOKEN=
```

Allowed exception:

```text
redacted variable metadata
empty placeholders
template examples
```

If a backup contains leaked secrets, status must be:

```text
FAIL_BLOCKING
```

and the operator must rotate affected secrets.

---

## 27. Disaster Recovery Model

For a lost Konnaxion Box or VPS:

```text
1. Install clean host.
2. Install Konnaxion Capsule Manager.
3. Import trusted capsule.
4. Import verified backup set.
5. Restore into new instance.
6. Generate new host-level secrets if required.
7. Apply safe network profile.
8. Run Security Gate.
9. Run healthchecks.
10. Only then expose to intranet/tunnel/public profile.
```

Command pattern:

```bash
kx capsule import konnaxion-v14-demo-2026.04.30.kxcap
kx instance restore-new \
  --from demo-001_20260430_230000_daily \
  --new-instance-id demo-001-restored \
  --network intranet_private
kx security check demo-001-restored
kx instance health demo-001-restored
```

---

## 28. Incident Recovery Rule

If the host is suspected compromised, do **not** use ordinary rollback as the final fix.

Use:

```text
clean host
trusted capsule
verified DB dump
verified media backup
rotated secrets
new SSH keys
new firewall policy
Security Gate PASS
```

Do not restore:

```text
old disk image
old Docker daemon state
old system users
old crontabs
old sudoers
old authorized_keys
old /tmp or /dev/shm
old unknown containers
```

The safe recovery unit is:

```text
clean capsule + verified application data
```

not:

```text
old server state
```

---

## 29. Manager UI Requirements

The Konnaxion Capsule Manager must expose backup/restore in a plug-and-play way.

Main backup screen:

```text
Backups

Instance: demo-001
Status: running
Last backup: 2026-04-30 23:00
Backup health: PASS
Retention: 14 daily / 8 weekly / 12 monthly

[Create Backup]
[Restore]
[Test Restore]
[Download Backup]
```

Restore screen:

```text
Restore Konnaxion Instance

Source backup:
  demo-001_20260430_230000_daily

Target:
  demo-001

This will restore:
  [x] Database
  [x] Media
  [ ] Network profile
  [ ] Capsule version

Safety:
  [x] Create pre-restore backup first
  [x] Run Security Gate after restore
  [x] Keep rollback point

[Restore]
```

Danger confirmation text:

```text
RESTORE demo-001
```

---

## 30. CLI Requirements

### 30.1 Public Operator CLI

Canonical operator-facing commands:

```bash
kx instance backup <KX_INSTANCE_ID>
kx instance backup <KX_INSTANCE_ID> --class manual
kx backup list <KX_INSTANCE_ID>
kx backup verify <BACKUP_ID>
kx backup test-restore <BACKUP_ID>
kx instance restore <KX_INSTANCE_ID> --from <BACKUP_ID>
kx instance restore-new --from <BACKUP_ID> --new-instance-id <NEW_INSTANCE_ID>
kx instance health <KX_INSTANCE_ID>
kx instance rollback <KX_INSTANCE_ID> --level capsule
kx instance rollback <KX_INSTANCE_ID> --level data --from <BACKUP_ID>
kx instance rollback <KX_INSTANCE_ID> --level full --from <BACKUP_ID>
```

The following commands should be added to the canonical CLI section of `DOC-00_Konnaxion_Canonical_Variables.md` if accepted:

```bash
kx backup list
kx backup verify
kx backup test-restore
kx instance restore-new
kx instance health
```

### 30.2 Internal Agent Operations

The following are internal Agent operations, not normal public CLI commands:

```text
backup_preflight
restore_preflight
restore_postflight
stop_selected_services
start_selected_services
fix_permissions
verify_forbidden_paths
scan_backup_for_secret_leaks
```

Implementations may expose debug/admin forms of these operations later, but they must not be required for normal plug-and-play operation.

---

## 31. Resource Status Values

The statuses below are **resource-specific statuses**, not canonical `Konnaxion Instance` states.

Canonical instance states remain defined in `DOC-00_Konnaxion_Canonical_Variables.md`.

### 31.1 Backup Statuses

```text
created
running
verifying
verified
failed
expired
deleted
quarantined
```

### 31.2 Restore Statuses

```text
planned
preflight
creating_pre_restore_backup
restoring_database
restoring_media
running_migrations
running_security_gate
running_healthchecks
restored
degraded
failed
rolled_back
```

### 31.3 Rollback Statuses

```text
planned
running
capsule_repointed
data_restored
healthchecking
completed
failed
```

These statuses should be mirrored in `DOC-00_Konnaxion_Canonical_Variables.md` if they become canonical across the full documentation set.

---

## 32. Failure Handling

If backup fails:

```text
do not mark backup as valid
keep logs
delete incomplete dump unless debugging enabled
return FAIL_BLOCKING if backup was required before update
```

If restore fails before database overwrite:

```text
abort restore
keep current instance unchanged
mark restore failed
```

If restore fails after database overwrite:

```text
attempt restore from pre-restore backup
keep failed backup logs
mark instance degraded or failed
```

If rollback fails:

```text
stop public exposure
switch to safest private profile
keep services stopped if integrity is unknown
show recovery instructions
```

---

## 33. File Naming

Backup ID format:

```text
<KX_INSTANCE_ID>_<YYYYMMDD_HHMMSS>_<BACKUP_CLASS>
```

Examples:

```text
demo-001_20260430_230000_daily
demo-001_20260430_173000_pre-update
demo-001_20260430_181500_manual
```

Archive file naming:

```text
postgres.dump
media.tar.zst
checksums.sha256
backup-manifest.yaml
```

---

## 34. Minimum Acceptance Criteria

A DOC-09-compliant backup system must satisfy:

```text
Can create a verified Postgres dump.
Can backup media separately.
Can generate backup-manifest.yaml.
Can verify checksums.
Can reject forbidden paths.
Can scan for leaked secrets.
Can restore into a new instance.
Can create pre-update backup.
Can perform capsule rollback.
Can block restore if Security Gate fails.
Can show simple Manager UI state.
```

---

## 35. MVP Implementation Plan

### Phase 1 — Manual-safe backups

```text
kx instance backup
kx backup list
kx backup verify
Postgres dump
media archive
backup manifest
checksums
```

### Phase 2 — Restore into new instance

```text
kx instance restore-new
local_only restore tests
healthchecks
Security Gate integration
```

### Phase 3 — Update rollback

```text
pre-update backup
capsule rollback
automatic rollback on healthcheck failure
```

### Phase 4 — Manager UI

```text
backup status page
restore wizard
test restore button
rollback button
```

### Phase 5 — Hardened disaster recovery

```text
off-host backup export
encrypted backup support
scheduled backup alerts
restore drills
```

---

## 36. Open Decisions

| Decision | Default for now |
|---|---|
| Backup encryption | Required later; not required for MVP if backups stay local and protected. |
| Offsite backup provider | Not fixed; must support offline/intranet use. |
| Backup compression | `zstd` preferred. |
| Postgres dump format | `custom` preferred. |
| Restore into same instance | Supported, but restore-new is safer. |
| Public demo backup behavior | Same as private; no secrets in backup. |
| Automatic data rollback | Only if update marks database as changed. |
| Canonical backup CLI location | Add runtime backup commands to DOC-00; keep DOC-10 builder-only unless CLI scope changes. |

---

## 37. Cross-Document Updates Required

To make this document fully canonical, update the following files:

```text
DOC-00_Konnaxion_Canonical_Variables.md
  Add backup variables, backup path convention, backup/restore/rollback statuses,
  and accepted runtime backup CLI commands.

DOC-05_Konnaxion_Agent_Security_Model.md
  Add backup/restore/rollback to the Agent allowlist and forbidden restore list.

DOC-06_Konnaxion_Network_Profiles.md
  Add restore behavior by network profile.

DOC-14_Konnaxion_Operator_Guide.md
  Add operator backup, restore, verify and rollback workflows.

DOC-12_Konnaxion_Install_Runbook.md
  Add backup directory setup and first backup verification.

DOC-11_Konnaxion_Box_Appliance_Image.md
  Add appliance-level backup storage, restore and factory reset behavior.
```

`DOC-10_Konnaxion_Builder_CLI.md` should only change if the project decides that DOC-10 documents all CLI commands. If DOC-10 remains builder-only, backup CLI should be documented in DOC-00, DOC-09 and DOC-14 instead.

---

## 38. Canonical Summary

```text
Konnaxion backup protects application data, not the host.
Konnaxion restore rebuilds into a trusted runtime, not an old system image.
Konnaxion rollback first reverts capsule code, then data only when necessary.
Konnaxion Manager must make backup/restore plug-and-play.
Konnaxion Agent must enforce safety rules and block dangerous restores.
```
