---
doc_id: DOC-12
title: Konnaxion Install Runbook
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
  - DOC-09_Konnaxion_Backup_Restore_Rollback.md
related_docs:
  - DOC-10_Konnaxion_Builder_CLI.md
  - DOC-11_Konnaxion_Box_Appliance_Image.md
  - DOC-13_Konnaxion_Threat_Model.md
  - DOC-14_Konnaxion_Operator_Guide.md
---

# DOC-12 — Konnaxion Install Runbook

---
## 1. Purpose

This runbook defines the standard installation process for a **Konnaxion Capsule** on a **Konnaxion Box**, local demo server, intranet machine, or hardened VPS.

The goal is plug-and-play operation:

```text
1. Prepare host or boot Konnaxion Box.
2. Open Konnaxion Capsule Manager.
3. Import .kxcap file.
4. Choose network profile.
5. Start instance.
6. Open generated URL.
```

The operator should not manually configure Docker Compose, Traefik, PostgreSQL, Redis, Celery, Django settings, Next.js runtime, certificates, ports, or firewall rules.

---

## 2. Installation model

The install process creates a **Konnaxion Instance** from a signed **Konnaxion Capsule**.

```text
Konnaxion Capsule (.kxcap)
  ↓ imported by
Konnaxion Capsule Manager
  ↓ controlled through
Konnaxion Agent
  ↓ creates
Konnaxion Instance
```

The capsule is immutable.

The instance is mutable.

```text
Capsule = app images + manifest + profiles + templates + checksums + signature
Instance = secrets + database + media + logs + backups + runtime state
```

---

## 3. Supported installation targets

| Target                     | Use case                           | Default profile    |
| -------------------------- | ---------------------------------- | ------------------ |
| `Konnaxion Box`            | Dedicated plug-and-play machine    | `intranet_private` |
| `Local demo host`          | Developer or demo machine          | `local_only`       |
| `Intranet server`          | School, organization, office LAN   | `intranet_private` |
| `Private remote demo host` | Access through Tailscale/VPN       | `private_tunnel`   |
| `Temporary demo host`      | Short-lived public access          | `public_temporary` |
| `Public VPS`               | Public production-style deployment | `public_vps`       |

The default must never be public.

```env
KX_NETWORK_PROFILE=intranet_private
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

---

## 4. Existing application stack

Konnaxion v14 uses:

```text
Frontend: Next.js / React / TypeScript
Backend: Django 5.1 + Django REST Framework
Database: PostgreSQL
Background jobs: Celery
Broker/result backend: Redis
Reverse proxy: Traefik
Media/static service: Nginx
Runtime target: Docker Compose
```

The v14 technical reference identifies Konnaxion as a Next.js frontend, Django + DRF backend, PostgreSQL primary database, and Celery + Redis background-processing stack. 

The current production Docker environment includes Django, Postgres, Redis, Traefik, Celery worker, Celery beat, Flower, and Nginx for static/media handling. 

---

## 5. Security baseline

Every install must follow these rules:

```text
private-by-default
deny-by-default firewall
signed capsules only
secrets generated on install
Traefik-only external entrypoint
PostgreSQL internal only
Redis internal only
Docker socket never exposed
no privileged containers
no host network mode
public temporary mode expires automatically
```

The previous Namecheap VPS incident included malicious Docker containers, miner activity, cron persistence, `/tmp/sshd`, `/dev/shm` executables, a `pakchoi` sudo backdoor attempt, and exposed secrets. The compromised VPS must not be trusted long-term and should not be cloned. 

---

## 6. Ports policy

### 6.1 Public or LAN entrypoints

|  Port | Usage                  | Rule                                               |
| ----: | ---------------------- | -------------------------------------------------- |
| `443` | HTTPS through Traefik  | allowed according to profile                       |
|  `80` | HTTP redirect to HTTPS | allowed for `public_vps`; optional for intranet    |
|  `22` | SSH                    | allowed only for maintenance, restricted by IP/VPN |

### 6.2 Forbidden public ports

These ports must never be exposed directly:

```text
3000/tcp  Next.js direct access
5000/tcp  Django/Gunicorn internal
5555/tcp  Flower or dashboard
5432/tcp  PostgreSQL
6379/tcp  Redis
8000/tcp  Django dev/server direct
Docker daemon TCP ports
```

Security notes from the incident recovery plan explicitly identify `3000`, `5555`, `5432`, `6379`, `8000`, and Docker daemon ports as non-public surfaces; public traffic should reach only Traefik on `80/443`. 

---

## 7. Required artifacts

Before installation, the operator must have:

```text
1. Konnaxion Capsule file:
   konnaxion-v14-demo-YYYY.MM.DD.kxcap

2. Konnaxion Capsule Manager installed or preloaded.

3. Konnaxion Agent running.

4. Docker runtime available.

5. Host with enough memory and disk.

6. Optional:
   - Tailscale account for private tunnel mode.
   - Cloudflare Tunnel credentials for temporary public mode.
   - VPS cloud firewall access for public_vps mode.
```

The capsule file must be produced by **Konnaxion Capsule Builder** and signed before distribution.

---

## 8. Hardware requirements

### 8.1 Minimum

```text
CPU: 2 cores
RAM: 4 GB
Disk: 80 GB SSD
Network: Ethernet preferred
OS: Ubuntu Server LTS or Konnaxion Box image
```

### 8.2 Recommended

```text
CPU: 4+ cores
RAM: 8–16 GB
Disk: 256 GB SSD/NVMe
Network: wired Ethernet
Power: UPS for intranet installations
```

The frontend deployment runbook confirms that `NODE_OPTIONS="--max-old-space-size=4096"` was required to avoid Next.js heap out-of-memory failures during production builds on limited-memory servers. 

For capsule installs, the frontend should normally be prebuilt inside the capsule. The memory note remains relevant for build hosts and builder machines.

---

## 9. Host preparation modes

## 9.1 Konnaxion Box mode

This is the preferred plug-and-play mode.

Expected starting point:

```text
Konnaxion Box image already installed
Konnaxion Capsule Manager preinstalled
Konnaxion Agent enabled
Docker installed
Firewall enabled
Default network profile: intranet_private
```

Operator flow:

```text
1. Plug machine into power.
2. Plug Ethernet.
3. Boot.
4. Open Konnaxion Capsule Manager.
5. Import .kxcap.
6. Click Start.
```

No shell access should be required for standard operation.

---

## 9.2 Generic Linux host mode

For a generic Ubuntu/Debian machine:

```bash
sudo apt update
sudo apt upgrade -y

sudo apt install -y \
  ca-certificates \
  curl \
  gnupg \
  ufw \
  fail2ban \
  unattended-upgrades
```

Install Docker according to the approved Konnaxion runtime package or appliance image process.

Enable baseline firewall:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

sudo ufw allow 443/tcp
sudo ufw allow 80/tcp

sudo ufw enable
sudo ufw status verbose
```

For a pure intranet host, `80/443` may be limited to private LAN ranges by the Agent profile.

---

## 9.3 Public VPS mode

Public VPS mode is not the default.

Use only for `KX_NETWORK_PROFILE=public_vps`.

Minimum baseline:

```text
Ubuntu Server LTS
SSH key only
root SSH disabled
password SSH disabled
cloud firewall enabled
UFW enabled
Fail2Ban enabled
unattended security updates enabled
provider snapshots/backups enabled
```

Public VPS firewall:

```text
Allow 80/tcp from anywhere
Allow 443/tcp from anywhere
Allow 22/tcp only from admin IP or VPN
Deny everything else
```

The incident recovery guidance recommends a fresh VPS, no disk clone, clean source deploy, verified DB/media restore only, full secret rotation, SSH keys only, password login disabled, cloud firewall + UFW, and only ports `22`, `80`, and `443` public. 

---

## 10. First install flow

The standard first-run flow is:

```text
1. Open Konnaxion Capsule Manager.
2. Select “Import Capsule”.
3. Choose .kxcap file.
4. Manager sends capsule to Konnaxion Agent.
5. Agent verifies signature.
6. Agent validates manifest.
7. Agent loads approved images.
8. Agent creates instance directory.
9. Agent creates canonical backup root.
10. Agent generates secrets.
11. Operator chooses network profile.
12. Agent runs Security Gate.
13. Agent starts runtime.
14. Agent runs migrations.
15. Agent runs healthchecks.
16. Agent creates and verifies initial backup.
17. Manager displays URL, status and backup health.
```

The operator should only choose:

```text
Instance name
Network profile
Admin account option
```

Everything else is automatic.

Install is complete only when the instance is running, the Security Gate is `PASS`, healthchecks pass, and the initial backup is verified.

---

## 11. Import capsule

### 11.1 UI path

```text
Konnaxion Capsule Manager
  → Capsules
  → Import Capsule
  → Select .kxcap
```

### 11.2 CLI equivalent

```bash
kx capsule import ./konnaxion-v14-demo-2026.04.30.kxcap
```

Expected result:

```text
Capsule imported
Signature: PASS
Manifest: PASS
Images: PASS
Capsule state: ready
```

If signature verification fails:

```text
State: security_blocked
Action: reject capsule
```

Do not provide an override button in normal UI.

---

## 12. Create instance

### 12.1 UI path

```text
Konnaxion Capsule Manager
  → Capsules
  → konnaxion-v14-demo-2026.04.30
  → Create Instance
```

Required fields:

```text
Instance name: demo-001
Network profile: intranet_private
Admin account: auto-generate or user-provided
```

### 12.2 CLI equivalent

```bash
kx instance create \
  --capsule konnaxion-v14-demo-2026.04.30 \
  --instance demo-001 \
  --network intranet_private
```

Expected instance path:

```text
/opt/konnaxion/instances/demo-001/
├── env/
├── postgres/
├── redis/
├── media/
├── logs/
├── backups/
└── state/
```

---

## 13. Secret generation

During instance creation, the Agent generates:

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
internal service tokens
admin bootstrap token
profile-specific hostnames
local TLS material if needed
```

The capsule must contain only templates, never real secrets.

Example generated env target:

```text
/opt/konnaxion/instances/demo-001/env/.django
/opt/konnaxion/instances/demo-001/env/.postgres
/opt/konnaxion/instances/demo-001/env/.frontend
```

If installing after a compromised server incident, rotate:

```text
SSH keys
deploy passwords
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
DATABASE_URL
Neon/database credentials
Django admin passwords
API keys
tokens
private keys
```

The recovery notes specifically instruct rotating these credentials and avoiding `.env` leaks in logs or chat. 

---

## 14. Choose network profile

Supported profiles:

```text
local_only
intranet_private
private_tunnel
public_temporary
public_vps
offline
```

### 14.1 local_only

```text
URL: https://localhost
Exposure: same machine only
Ports: localhost only
```

### 14.2 intranet_private

```text
URL: https://konnaxion.local or generated LAN hostname
Exposure: private LAN only
Ports: 443 on LAN
Public Internet: no
```

### 14.3 private_tunnel

```text
URL: private tunnel hostname
Exposure: VPN/tailnet only
Router ports: none
Public Internet: no
```

### 14.4 public_temporary

```text
URL: temporary public tunnel
Expiration: required
Authentication: recommended
Router ports: none
```

### 14.5 public_vps

```text
URL: https://domain
Exposure: public 80/443
Cloud firewall: required
SSH hardening: required
```

### 14.6 offline

```text
URL: local only or none
Network: disabled except internal container network
```

---

## 15. Security Gate

Before start, the Agent must run:

```bash
kx security check demo-001
```

Required checks:

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

Allowed statuses:

```text
PASS
WARN
FAIL_BLOCKING
SKIPPED
UNKNOWN
```

Start is allowed only if all critical checks return:

```text
PASS
SKIPPED
```

Start must be blocked if any critical check returns:

```text
FAIL_BLOCKING
UNKNOWN
```

---

## 16. Start instance

### 16.1 UI path

```text
Konnaxion Capsule Manager
  → Instances
  → demo-001
  → Start
```

### 16.2 CLI equivalent

```bash
kx instance start demo-001
```

Expected lifecycle:

```text
verifying
starting
migrating
healthchecking
running
```

Expected services:

```text
traefik
frontend-next
django-api
postgres
redis
celeryworker
celerybeat
media-nginx
```

Optional/private:

```text
flower
```

---

## 17. Runtime startup sequence

The Agent must start services in this order:

```text
1. Create Docker networks.
2. Create volumes.
3. Start postgres.
4. Start redis.
5. Run database readiness check.
6. Run Django migrations.
7. Start django-api.
8. Start celeryworker.
9. Start celerybeat.
10. Start media-nginx.
11. Start frontend-next.
12. Start traefik.
13. Run healthchecks.
14. Mark instance running.
```

Production capsule installs must run:

```bash
python manage.py migrate
```

They must not run:

```bash
python manage.py makemigrations
```

Migration files must already be included in the capsule.

The existing backend workflow confirms the required operational pattern: build/start Docker services, generate migrations during development, apply `migrate`, verify service status, and optionally create a superuser. For capsule runtime, only `migrate` belongs in the install path. 

---

## 18. Verify installation

### 18.1 Manager UI

Expected status:

```text
Instance: demo-001
State: running
Network profile: intranet_private
Exposure: private
Security Gate: PASS
Healthchecks: PASS
Backup: PASS
Backup root: /opt/konnaxion/backups/demo-001
Public mode: disabled
```

The install is not complete if backup status is missing, unverified, failed, quarantined, or unknown.

### 18.2 CLI

```bash
kx instance status demo-001
kx security check demo-001
kx instance logs demo-001 --tail 100
```

Expected services:

```text
traefik: healthy
frontend-next: healthy
django-api: healthy
postgres: healthy
redis: healthy
celeryworker: healthy
celerybeat: healthy
media-nginx: healthy
```

### 18.3 Initial backup validation

A first verified backup must exist after install.

```bash
kx instance backup demo-001 --class manual
kx backup list demo-001
kx backup verify <BACKUP_ID>
```

Expected backup state:

```text
Backup status: verified
Backup class: manual
Backup root: /opt/konnaxion/backups/demo-001/
Security Gate: PASS
Secrets included: false
Forbidden paths included: false
```

The Manager UI should show:

```text
Backup health: PASS
Last backup: <timestamp>
Restore readiness: PASS
```

### 18.4 HTTP checks

For local mode:

```bash
curl -k -I https://localhost/
curl -k -I https://localhost/api/
curl -k -I https://localhost/admin/
```

For intranet mode:

```bash
curl -k -I https://konnaxion.local/
curl -k -I https://konnaxion.local/api/
curl -k -I https://konnaxion.local/admin/
```

For public VPS mode:

```bash
curl -I https://<KONNAXION_PUBLIC_HOST>/
curl -I https://<KONNAXION_PUBLIC_HOST>/api/
curl -I https://<KONNAXION_PUBLIC_HOST>/admin/
```

The legacy deployment guide expects `/` to route to Next.js, `/api/` to Django, `/admin/` to Django admin, and `/media/` to the media service.

---

## 19. Verify blocked ports

Run:

```bash
sudo ss -tulpen
```

There must be no public listeners for:

```text
0.0.0.0:3000
0.0.0.0:5000
0.0.0.0:5555
0.0.0.0:5432
0.0.0.0:6379
0.0.0.0:8000
```

For `public_vps`, expected external exposure:

```text
0.0.0.0:80
0.0.0.0:443
restricted:22
```

For `intranet_private`, expected exposure is profile-specific and should be LAN-only.

---

## 20. Admin bootstrap

During first install, the operator chooses one of:

```text
Auto-generate admin account
Create admin account manually
Import admin bootstrap file
```

### 20.1 Auto-generate

The Agent creates:

```text
username: generated or provided
temporary password: generated once
must_change_password: true
```

The Manager displays the temporary password once.

### 20.2 Manual CLI fallback

```bash
kx instance exec demo-001 django-api -- python manage.py createsuperuser
```

This should be hidden from standard users and used only by operators.

---

## 21. Backup configuration

Backups must be enabled by default.

```env
KX_BACKUP_ENABLED=true
KX_BACKUP_RETENTION_DAYS=14
KX_BACKUP_ROOT=/opt/konnaxion/backups
```

### 21.1 Canonical backup storage

Canonical backup storage:

```text
/opt/konnaxion/backups/<KX_INSTANCE_ID>/
```

Example:

```text
/opt/konnaxion/backups/demo-001/
├── daily/
├── weekly/
├── monthly/
├── pre-update/
├── pre-restore/
└── manual/
```

The instance-local backup directory is not the canonical storage root. It may exist only as a pointer, cache or state directory:

```text
/opt/konnaxion/instances/<KX_INSTANCE_ID>/backups/
```

### 21.2 Backup directory creation

During install, the Agent must create and validate:

```bash
sudo mkdir -p /opt/konnaxion/backups/demo-001/{daily,weekly,monthly,pre-update,pre-restore,manual}
sudo chown -R kx-agent:konnaxion /opt/konnaxion/backups/demo-001
sudo chmod -R 750 /opt/konnaxion/backups/demo-001
```

The exact user/group may vary by appliance implementation, but the directory must not be world-readable.

### 21.3 Backup contents

Backup contents:

```text
PostgreSQL logical dump
media files
instance metadata
redacted env metadata without secret values
capsule reference
manifest reference
network profile
Security Gate result
healthcheck result
checksums
```

### 21.4 Forbidden backup contents

Do not back up:

```text
/tmp
/dev/shm
host crontabs
unknown systemd services
old authorized_keys
old sudoers files
unknown Docker volumes
Docker daemon state
old compromised disk images
plaintext secrets
```

The incident recovery rule is that backups must recover application data, not preserve malware or host persistence.

### 21.5 Initial verified backup

After the first successful install, the Agent must create a first verified backup.

```bash
kx instance backup demo-001 --class manual
kx backup verify <BACKUP_ID>
```

Expected output:

```text
Backup created:
backup_id: demo-001_YYYYMMDD_HHMMSS_manual
backup_root: /opt/konnaxion/backups/demo-001/manual/demo-001_YYYYMMDD_HHMMSS_manual
status: verified
```

The Manager UI must show:

```text
Backup health: PASS
Last backup: <timestamp>
Restore readiness: PASS
```

A Konnaxion Instance is not considered fully installed until backup verification passes.

---

## 22. Update instance

Update requires a new signed capsule.

```bash
kx capsule import ./konnaxion-v14-demo-2026.05.01.kxcap
kx instance update demo-001 --capsule konnaxion-v14-demo-2026.05.01
```

Update flow:

```text
1. Verify new capsule.
2. Run Security Gate pre-check.
3. Backup current instance.
4. Stop app services.
5. Apply new capsule references.
6. Run migrations.
7. Start services.
8. Run healthchecks.
9. Mark update complete.
```

If healthcheck fails, rollback begins automatically.

---

## 23. Rollback instance

Manual rollback:

```bash
kx instance rollback demo-001
```

Rollback flow:

```text
1. Stop failed services.
2. Restore previous capsule pointer.
3. Restore previous runtime config if needed.
4. Restore DB backup if migration is not backward-compatible.
5. Start previous stack.
6. Run healthchecks.
7. Mark running or degraded.
```

Rollback is only safe if the previous backup exists and the database migration is either backward-compatible or restored.

---

## 24. Public temporary mode

Public temporary mode is for short external demos only.

Rules:

```text
KX_PUBLIC_MODE_ENABLED=true
KX_PUBLIC_MODE_EXPIRES_AT required
authentication recommended
automatic expiration required
manual permanent public exposure forbidden
```

Start temporary access:

```bash
kx network set-profile demo-001 public_temporary \
  --duration-hours 2
```

Expected:

```text
Temporary public URL generated
Expiration set
Security Gate passed
```

After expiration:

```text
Public tunnel closed
KX_PUBLIC_MODE_ENABLED=false
Network profile returns to previous private profile
```

---

## 25. Public VPS mode

Public VPS mode is for real public deployment.

Preconditions:

```text
fresh VPS
not cloned from compromised server
cloud firewall configured
SSH key-only authentication
password login disabled
root login disabled
UFW enabled
Fail2Ban enabled
unattended upgrades enabled
backups/snapshots enabled
```

The new deployment must not reuse old secrets or old server state.

The recovery plan recommends clean Git/source deployment, verified DB dump/media only, full secret rotation, firewall before app exposure, and validating access only through `80/443`. 

---

## 26. Uninstall instance

Stop instance:

```bash
kx instance stop demo-001
```

Create final backup:

```bash
kx instance backup demo-001
```

Remove instance:

```bash
kx instance remove demo-001
```

The Manager must clearly distinguish:

```text
Remove instance but keep backups
Remove instance and delete backups
```

Default:

```text
keep backups
```

---

## 27. Decommission host

For a host that is no longer trusted:

```text
1. Export verified DB dump.
2. Export required media only.
3. Copy backups off-host.
4. Rotate secrets.
5. Destroy VPS or wipe disk.
6. Do not reuse Docker volumes.
7. Do not reuse SSH keys.
8. Do not reuse authorized_keys.
9. Do not reuse crontabs.
10. Do not reuse systemd services.
```

For compromised hosts, never create a new Konnaxion Box image from that disk.

---

## 28. Troubleshooting

## 28.1 Capsule import fails

Symptoms:

```text
Signature: FAIL_BLOCKING
Manifest: FAIL_BLOCKING
Image checksum mismatch
```

Action:

```text
Reject capsule.
Do not start instance.
Rebuild capsule from trusted source.
```

---

## 28.2 Security Gate blocks start

Check:

```bash
kx security check demo-001
```

Common causes:

```text
dangerous port exposed
Docker socket mounted
unknown image found
Postgres exposed publicly
Redis exposed publicly
firewall disabled
public mode missing expiration
```

Action:

```text
Fix profile or capsule.
Re-run Security Gate.
Do not bypass.
```

---

## 28.3 Database migration fails

Check logs:

```bash
kx instance logs demo-001 --service django-api --tail 200
kx instance logs demo-001 --service postgres --tail 200
```

Action:

```text
Stop update.
Keep backup.
Rollback if needed.
Do not run makemigrations on target host.
```

---

## 28.4 Frontend fails healthcheck

Check:

```bash
kx instance logs demo-001 --service frontend-next --tail 200
```

Possible causes:

```text
bad baked API URL
missing production build
memory-related build problem on builder
```

The legacy frontend runbook notes that production frontend values are baked at build time and that `.next/BUILD_ID` must exist before starting Next.js. 

In capsule mode, frontend should be prebuilt during capsule build.

---

## 28.5 Public URL works but API fails

Check routing:

```bash
curl -I https://<HOST>/
curl -I https://<HOST>/api/
curl -I https://<HOST>/admin/
curl -I https://<HOST>/media/
```

Expected routing:

```text
/        -> frontend-next
/api/    -> django-api
/admin/  -> django-api
/media/  -> media-nginx
```

If `/api/` fails, inspect:

```bash
kx instance logs demo-001 --service traefik --tail 200
kx instance logs demo-001 --service django-api --tail 200
```

---

## 28.6 Suspicious host state

Run host inspection:

```bash
echo "== users =="
cut -d: -f1,3,7 /etc/passwd | sort

echo "== sudoers =="
sudo ls -la /etc/sudoers.d
sudo grep -R . /etc/sudoers.d /etc/sudoers 2>/dev/null

echo "== cron =="
sudo crontab -l || true
crontab -l || true
sudo ls -la /etc/cron.* /var/spool/cron/crontabs 2>/dev/null

echo "== suspicious tmp/shm =="
sudo find /tmp /dev/shm -maxdepth 2 -type f -executable -ls 2>/dev/null

echo "== ports =="
sudo ss -tulpen

echo "== docker =="
docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
docker images 2>/dev/null || true
```

Look for:

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
unknown Docker containers
```

These indicators match the previous compromise pattern. 

---

## 29. Standard install checklist

Before install:

```text
[ ] Host is fresh or trusted.
[ ] Host is not cloned from compromised VPS.
[ ] Konnaxion Capsule Manager installed.
[ ] Konnaxion Agent running.
[ ] Docker runtime available.
[ ] Firewall enabled.
[ ] .kxcap file available.
[ ] Capsule source trusted.
```

During install:

```text
[ ] Capsule imported.
[ ] Signature PASS.
[ ] Manifest PASS.
[ ] Images PASS.
[ ] Instance created.
[ ] Secrets generated.
[ ] Network profile selected.
[ ] Security Gate PASS.
[ ] Runtime started.
[ ] Migrations applied.
[ ] Healthchecks PASS.
[ ] Initial backup PASS.
```

After install:

```text
[ ] URL opens.
[ ] /api/ responds.
[ ] /admin/ responds.
[ ] /media/ responds if media is present.
[ ] No dangerous ports public.
[ ] Backup root created.
[ ] Initial backup created.
[ ] Initial backup verified.
[ ] Manager UI shows Backup health PASS.
[ ] Admin account created.
[ ] Public mode disabled unless explicitly required.
[ ] Logs show no secret leakage.
```

---

## 30. Operator quick path

For standard intranet install:

```bash
kx capsule import ./konnaxion-v14-demo-2026.04.30.kxcap

kx instance create \
  --capsule konnaxion-v14-demo-2026.04.30 \
  --instance demo-001 \
  --network intranet_private

kx security check demo-001

kx instance start demo-001

kx instance status demo-001

kx instance backup demo-001 --class manual
kx backup list demo-001
kx backup verify <BACKUP_ID>
```

Expected final state:

```text
Instance: demo-001
State: running
Network profile: intranet_private
Exposure: private
Security Gate: PASS
Backup health: PASS
Restore readiness: PASS
URL: https://konnaxion.local or generated LAN URL
```

---

## 31. Non-goals

This runbook does not cover:

```text
Building a capsule from source
Changing application code
Writing migrations
Designing Docker images
Generic Docker hosting
Kubernetes deployment
Recovering secrets from compromised hosts
Cloning old VPS disks
Running arbitrary third-party apps
```

Those are covered by other documents or explicitly out of scope.

---

## 32. Summary

The Konnaxion install process must be:

```text
plug-and-play
private-by-default
security-gated
capsule-driven
repeatable
rollback-capable
operator-safe
```

The canonical install path is:

```text
Import signed .kxcap
Create Konnaxion Instance
Generate secrets
Choose network profile
Run Security Gate
Start Docker Compose runtime
Apply migrations
Run healthchecks
Create backup root
Create and verify initial backup
Display URL
```

The user should configure only:

```text
Instance name
Network profile
Admin account option
```

Everything else is handled by the **Konnaxion Capsule Manager** and **Konnaxion Agent**.
