---
doc_id: DOC-06
title: Konnaxion Network Profiles
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: draft
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-04_Konnaxion_Manager_Architecture.md
  - DOC-05_Konnaxion_Agent_Security_Model.md
  - DOC-07_Konnaxion_Security_Gate.md
owner: Konnaxion Architecture
last_updated: 2026-04-30
default_network_profile: intranet_private
default_exposure_mode: private
---

# DOC-06 — Konnaxion Network Profiles

## 1. Purpose

This document defines the canonical network profiles used by the **Konnaxion Capsule Manager** and enforced by the **Konnaxion Agent**.

The goal is to make Konnaxion deployable as a plug-and-play capsule while keeping network exposure predictable, minimal, and secure.

Konnaxion must be **private-by-default**.

The user should not manually configure Docker ports, Traefik routers, Redis exposure, PostgreSQL exposure, Django binding, Next.js binding, or firewall rules.

The user chooses a network profile. The Manager applies the correct network policy.

---

## 2. Grounding

Konnaxion v14 uses a **Next.js frontend**, **Django + DRF backend**, **PostgreSQL**, **Celery + Redis**, and Docker-oriented deployment infrastructure. The canonical runtime model is defined in `DOC-00_Konnaxion_Canonical_Variables.md` and `DOC-08_Konnaxion_Runtime_Docker_Compose.md`.

The canonical production topology includes Traefik as the only HTTP(S) entrypoint, with routing from `/` to `frontend-next`, `/api/` and `/admin/` to `django-api`, and `/media/` to `media-nginx`.

The security baseline is based on the incident recovery notes and `DOC-07_Konnaxion_Security_Gate.md`: public users should reach only the reverse proxy on `80/443`; ports such as `3000`, `5555`, `5432`, `6379`, `8000`, and Docker daemon ports must not be public.

---

## 3. Canonical Profiles

The only valid values for `KX_NETWORK_PROFILE` are:

```text
offline
local_only
intranet_private
private_tunnel
public_temporary
public_vps
```

Default:

```env
KX_NETWORK_PROFILE=intranet_private
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

Public mode is never the default.

---

## 4. Profile Summary Matrix

| Profile          | Variable           |             Intended use | Public internet |      LAN | VPN/Tunnel | Default |
| ---------------- | ------------------ | -----------------------: | --------------: | -------: | ---------: | ------: |
| Offline          | `offline`          | Fully isolated demo/test |              no |       no |         no |      no |
| Local only       | `local_only`       |     Demo on same machine |              no |       no |         no |      no |
| Intranet private | `intranet_private` |     LAN/institution demo |              no |      yes |         no | **yes** |
| Private tunnel   | `private_tunnel`   |     Trusted remote users |              no | optional |        yes |      no |
| Public temporary | `public_temporary` |       External demo link |         limited | optional |     tunnel |      no |
| Public VPS       | `public_vps`       |   Real public deployment |             yes |      n/a |   optional |      no |

---

## 5. Shared Runtime Topology

All network profiles use the same internal service model.

```text
Client
  ↓
Traefik
  ├── /        -> frontend-next
  ├── /api/    -> django-api
  ├── /admin/  -> django-api
  └── /media/  -> media-nginx

Internal only:
  ├── postgres
  ├── redis
  ├── celeryworker
  ├── celerybeat
  └── flower
```

Only Traefik is allowed to be an external entrypoint.

Direct access to `frontend-next`, `django-api`, `postgres`, `redis`, `celeryworker`, `celerybeat`, `flower`, or Docker daemon is forbidden unless a future document explicitly defines an admin-only maintenance channel.

---

## 6. Global Forbidden Exposure

The following ports must never be exposed to the public internet:

```text
3000/tcp  Next.js direct access
5000/tcp  Django/Gunicorn internal service
5555/tcp  Flower or dashboard surface
5432/tcp  PostgreSQL
6379/tcp  Redis
8000/tcp  Django dev/server direct
2375/tcp  Docker daemon TCP without TLS
2376/tcp  Docker daemon TCP with TLS
```

The following services must always remain internal:

```text
postgres
redis
celeryworker
celerybeat
flower
django-api direct port
frontend-next direct port
Docker socket
```

The Docker socket must never be mounted into an application container.

```yaml
forbidden_mounts:
  - /var/run/docker.sock
```

---

## 7. Profile: `offline`

## 7.1 Purpose

`offline` is for isolated demos, testing, forensic inspection, or training where Konnaxion should not be reachable from any other device.

## 7.2 Exposure

```env
KX_NETWORK_PROFILE=offline
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

Allowed inbound:

```text
none
```

Allowed bind addresses:

```text
127.0.0.1 only
```

Network policy:

```text
No LAN exposure
No public exposure
No tunnel exposure
No router port forwarding
No external DNS dependency
```

## 7.3 URL

```text
https://localhost
```

Optional fallback:

```text
http://localhost
```

## 7.4 Firewall Policy

```text
deny incoming
allow outgoing only if required for updates
no inbound exception required
```

## 7.5 Security Gate Requirements

Required `PASS` checks:

```text
capsule_signature
image_checksums
manifest_schema
secrets_present
secrets_not_default
postgres_not_public
redis_not_public
docker_socket_not_mounted
no_privileged_containers
no_host_network
dangerous_ports_blocked
```

---

## 8. Profile: `local_only`

## 8.1 Purpose

`local_only` is for demos on the same machine where Konnaxion is opened from the host browser.

This profile is useful for developer machines, trade show laptops, and pre-demo validation.

## 8.2 Exposure

```env
KX_NETWORK_PROFILE=local_only
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

Allowed inbound:

```text
127.0.0.1:443
127.0.0.1:80 optional redirect only
```

Forbidden:

```text
0.0.0.0:3000
0.0.0.0:5000
0.0.0.0:5555
0.0.0.0:5432
0.0.0.0:6379
0.0.0.0:8000
```

## 8.3 URL

Primary:

```text
https://localhost
```

Optional named local URL:

```text
https://konnaxion.localhost
```

## 8.4 TLS Strategy

Use one of:

```text
self-signed local certificate
locally trusted development certificate
HTTP fallback for controlled local-only demo
```

Let’s Encrypt must not be used for `.local` or other non-public hostnames. The previous deployment notes explicitly warn that Let’s Encrypt cannot issue certificates for `.local`. 

## 8.5 Manager UI Label

```text
Local only
Accessible only from this computer.
Recommended for testing and private demos.
```

---

## 9. Profile: `intranet_private`

## 9.1 Purpose

`intranet_private` is the default profile.

It is used when a Konnaxion Box is plugged into a trusted private LAN such as:

```text
school network
community organization network
office LAN
demo room LAN
local lab network
```

## 9.2 Exposure

```env
KX_NETWORK_PROFILE=intranet_private
KX_EXPOSURE_MODE=lan
KX_PUBLIC_MODE_ENABLED=false
```

Allowed inbound:

```text
LAN:443/tcp
LAN:80/tcp optional redirect only
```

Forbidden inbound:

```text
Internet:any
LAN:3000
LAN:5000
LAN:5555
LAN:5432
LAN:6379
LAN:8000
Docker daemon
```

## 9.3 Allowed Source Ranges

Allowed private source ranges:

```text
10.0.0.0/8
172.16.0.0/12
192.168.0.0/16
fd00::/8
fe80::/10
```

The Manager may detect the active LAN subnet and restrict access to that subnet only.

Example:

```env
KX_ALLOWED_LAN_CIDR=192.168.1.0/24
```

## 9.4 URL

Preferred:

```text
https://konnaxion.local
```

Fallback:

```text
https://<LAN_IP>
```

Optional organization-specific hostname:

```text
https://konnaxion.intranet
https://konnaxion.school.lan
```

## 9.5 TLS Strategy

Allowed:

```text
self-signed local CA
locally trusted intranet certificate
organization-provided certificate
HTTP only if explicitly accepted for temporary LAN demo
```

Not allowed:

```text
Let’s Encrypt for .local
public DNS requirement by default
```

## 9.6 Firewall Policy

The Konnaxion Agent must apply:

```text
deny incoming by default
allow 443/tcp from KX_ALLOWED_LAN_CIDR
allow 80/tcp from KX_ALLOWED_LAN_CIDR only if redirect is enabled
deny 3000/tcp
deny 5000/tcp
deny 5555/tcp
deny 5432/tcp
deny 6379/tcp
deny 8000/tcp
deny Docker daemon ports
```

## 9.7 Manager UI Label

```text
Intranet private
Accessible from this local network only.
Recommended default.
```

## 9.8 Security Gate Requirements

Required `PASS` checks:

```text
firewall_enabled
lan_scope_detected
public_ip_not_exposed
dangerous_ports_blocked
postgres_not_public
redis_not_public
docker_socket_not_mounted
admin_surface_private
```

---

## 10. Profile: `private_tunnel`

## 10.1 Purpose

`private_tunnel` is for remote access by trusted users without opening router ports.

Examples:

```text
Tailscale
WireGuard
ZeroTier
organization VPN
```

## 10.2 Exposure

```env
KX_NETWORK_PROFILE=private_tunnel
KX_EXPOSURE_MODE=vpn
KX_PUBLIC_MODE_ENABLED=false
```

Allowed inbound:

```text
VPN/tunnel interface:443/tcp
VPN/tunnel interface:80/tcp optional redirect only
```

Forbidden:

```text
public internet direct access
router port forwarding
public 3000
public 5555
public 5432
public 6379
public 8000
```

## 10.3 URL

Example:

```text
https://konnaxion-demo.<tailnet>.ts.net
```

Generic:

```text
https://<PRIVATE_TUNNEL_HOST>
```

## 10.4 Required Variables

```env
KX_NETWORK_PROFILE=private_tunnel
KX_EXPOSURE_MODE=vpn
KX_TUNNEL_PROVIDER=tailscale
KX_TUNNEL_HOST=<generated_or_configured_host>
KX_PUBLIC_MODE_ENABLED=false
```

## 10.5 Firewall Policy

```text
deny incoming by default
allow 443/tcp only on tunnel interface
allow 80/tcp only on tunnel interface if redirect enabled
deny 443/tcp on public interface
deny 80/tcp on public interface unless explicitly required
deny all dangerous ports on all interfaces
```

## 10.6 Manager UI Label

```text
Private tunnel
Accessible only to approved tunnel/VPN users.
No router port forwarding required.
```

---

## 11. Profile: `public_temporary`

## 11.1 Purpose

`public_temporary` is for short-lived external demos.

It allows a public link without converting the Konnaxion Box into a permanent public server.

Examples:

```text
client demo
investor demo
partner walkthrough
remote presentation
```

## 11.2 Exposure

```env
KX_NETWORK_PROFILE=public_temporary
KX_EXPOSURE_MODE=temporary_tunnel
KX_PUBLIC_MODE_ENABLED=true
```

Required:

```env
KX_PUBLIC_MODE_DURATION_HOURS=<1|2|4|8>
KX_PUBLIC_MODE_EXPIRES_AT=<ISO8601_TIMESTAMP>
```

The Manager must refuse this profile if `KX_PUBLIC_MODE_EXPIRES_AT` is empty.

## 11.3 Allowed Public Entry

Allowed:

```text
443/tcp through managed tunnel
```

Optional:

```text
80/tcp only for provider-managed HTTPS redirect
```

Forbidden:

```text
direct router port forwarding by default
permanent public exposure
public SSH
public Postgres
public Redis
public Flower
public Docker
public Next.js direct
public Django direct
```

## 11.4 Auth Requirement

At least one of the following must be enabled:

```text
tunnel provider access policy
one-time demo password
basic auth at proxy layer
email allowlist
temporary invite token
```

Default:

```env
KX_PUBLIC_TEMPORARY_AUTH_REQUIRED=true
```

## 11.5 Expiration

When the expiration time is reached, the Manager must:

```text
close tunnel
revoke temporary URL
remove temporary auth tokens
return KX_PUBLIC_MODE_ENABLED=false
return profile to intranet_private or local_only
write audit log entry
```

## 11.6 Manager UI Label

```text
Public temporary demo
Creates a time-limited public link.
Requires authentication.
Automatically expires.
```

## 11.7 Security Gate Requirements

Required `PASS` checks:

```text
public_mode_expiration_present
public_mode_auth_enabled
tunnel_provider_configured
direct_public_ports_blocked
dangerous_ports_blocked
admin_surface_private_or_auth_protected
postgres_not_public
redis_not_public
docker_socket_not_mounted
```

Blocking failure if:

```text
KX_PUBLIC_MODE_EXPIRES_AT is empty
KX_PUBLIC_TEMPORARY_AUTH_REQUIRED=false
public 3000 detected
public 5555 detected
public 5432 detected
public 6379 detected
public Docker daemon detected
```

---

## 12. Profile: `public_vps`

## 12.1 Purpose

`public_vps` is for a real public production deployment.

This profile is not the default and should not be used for demo boxes unless the host has been hardened as a public server.

## 12.2 Exposure

```env
KX_NETWORK_PROFILE=public_vps
KX_EXPOSURE_MODE=public
KX_PUBLIC_MODE_ENABLED=true
```

Allowed public inbound:

```text
80/tcp
443/tcp
```

SSH:

```text
22/tcp only from admin IP or VPN
```

Forbidden public inbound:

```text
3000/tcp
5000/tcp
5555/tcp
5432/tcp
6379/tcp
8000/tcp
Docker daemon TCP ports
```

The incident recovery notes define the same production baseline: expose only `22`, `80`, and `443`, with SSH ideally limited to the administrator IP, and do not expose Next.js direct, Flower/dashboard, Postgres, Redis, Django/Gunicorn, or Docker daemon ports. 

## 12.3 URL

Example:

```text
https://konnaxion.com
https://www.konnaxion.com
```

## 12.4 TLS Strategy

Use public certificate automation only for valid public DNS names.

Allowed:

```text
Let’s Encrypt for valid public domain
provider-managed certificate
organization-managed certificate
```

Forbidden:

```text
Let’s Encrypt for .local
self-signed certificate for public production
```

## 12.5 Firewall Policy

Cloud firewall:

```text
allow 80/tcp from anywhere
allow 443/tcp from anywhere
allow 22/tcp only from admin IP or VPN
deny everything else
```

Host firewall:

```text
deny incoming by default
allow 80/tcp
allow 443/tcp
allow 22/tcp only from admin IP or VPN
deny dangerous ports
```

## 12.6 Manager UI Label

```text
Public VPS
Permanent public web deployment.
Requires hardened server and restricted SSH.
```

---

## 13. Traefik Routing Contract

All profiles must use this canonical route map:

```text
/        -> frontend-next
/api/    -> django-api
/admin/  -> django-api
/media/  -> media-nginx
```

No profile may expose:

```text
http://<host>:3000
http://<host>:5000
http://<host>:5555
http://<host>:5432
http://<host>:6379
http://<host>:8000
```

The frontend may be reachable internally at `frontend-next:3000`, but not externally.

The Django API may be reachable internally at `django-api:5000`, but not externally.

PostgreSQL and Redis must be reachable only through Docker private networks.

---

## 14. Hostname Policy

## 14.1 Local Hostnames

Allowed for `local_only`:

```text
localhost
127.0.0.1
konnaxion.localhost
```

## 14.2 Intranet Hostnames

Allowed for `intranet_private`:

```text
konnaxion.local
konnaxion.lan
custom organization LAN hostname
LAN IP fallback
```

## 14.3 Tunnel Hostnames

Allowed for `private_tunnel`:

```text
provider-generated private hostname
tailnet hostname
organization VPN DNS name
```

## 14.4 Public Hostnames

Allowed for `public_temporary`:

```text
temporary tunnel hostname
controlled demo subdomain
```

Allowed for `public_vps`:

```text
valid public DNS hostname
```

Examples:

```text
konnaxion.com
www.konnaxion.com
demo.konnaxion.com
```

---

## 15. Environment Output Contract

When a profile is applied, the Manager must generate environment values for both backend and frontend.

## 15.1 Django

```env
DJANGO_ALLOWED_HOSTS=<generated_from_profile>
CSRF_TRUSTED_ORIGINS=<generated_from_profile>
```

## 15.2 Frontend

```env
NEXT_PUBLIC_API_BASE=https://<PROFILE_HOST>/api
NEXT_PUBLIC_BACKEND_BASE=https://<PROFILE_HOST>
```

Because Next.js bakes public environment values at build time, a profile change that modifies public frontend URLs may require rebuilding or using a runtime configuration strategy.

## 15.3 Manager

```env
KX_NETWORK_PROFILE=<profile>
KX_EXPOSURE_MODE=<mode>
KX_PUBLIC_MODE_ENABLED=<true|false>
KX_PUBLIC_MODE_EXPIRES_AT=<timestamp_or_empty>
KX_ALLOWED_LAN_CIDR=<cidr_or_empty>
KX_TUNNEL_PROVIDER=<provider_or_empty>
KX_TUNNEL_HOST=<hostname_or_empty>
```

---

## 16. Profile Switching Rules

Allowed transitions:

```text
offline -> local_only
offline -> intranet_private
local_only -> intranet_private
intranet_private -> private_tunnel
intranet_private -> public_temporary
private_tunnel -> intranet_private
public_temporary -> intranet_private
public_vps -> public_vps
```

Restricted transitions:

```text
any -> public_vps
```

`public_vps` requires explicit operator confirmation and a successful hardening check.

Automatic transition:

```text
public_temporary -> intranet_private
```

This happens when `KX_PUBLIC_MODE_EXPIRES_AT` is reached.

---

## 17. Backup, Restore and Rollback Network Behavior

Backup, restore and rollback workflows are defined in `DOC-09_Konnaxion_Backup_Restore_Rollback.md`, but network behavior is governed by this document.

The network profile selected during restore must never weaken the Security Gate.

Default restore target:

```env
KX_RESTORE_DEFAULT_NETWORK_PROFILE=local_only
```

The safest restore target is `local_only` because it allows validation before LAN, tunnel, or public exposure.

## 17.1 Restore Behavior by Profile

| Target profile | Restore behavior |
|---|---|
| `offline` | Allowed only for isolated validation. No network exposure. |
| `local_only` | Default and safest restore target. Used for restore tests and high-risk recovery. |
| `intranet_private` | Allowed after Security Gate `PASS`; exposes Traefik to LAN only. |
| `private_tunnel` | Allowed only after tunnel configuration is validated. No router port forwarding. |
| `public_temporary` | Must not auto-enable public access after restore. Requires explicit operator action, auth, and expiration. |
| `public_vps` | Requires explicit approval, hardened firewall, SSH hardening, backups enabled, and Security Gate `PASS`. |

## 17.2 Restore Into New Instance

A restore into a new instance must default to:

```env
KX_NETWORK_PROFILE=local_only
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

The operator may switch the restored instance to `intranet_private`, `private_tunnel`, `public_temporary`, or `public_vps` only after:

```text
backup verification passed
restore preflight passed
restore postflight passed
Security Gate passed
healthchecks passed
dangerous ports remain blocked
```

## 17.3 Restore Into Existing Instance

A restore into an existing instance must preserve the current network profile only if the profile is still valid and safe.

If the current profile is unsafe, unknown, expired, or incompatible, the Agent must fall back to:

```env
KX_NETWORK_PROFILE=local_only
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

## 17.4 Public Temporary Restore Rule

A restored instance must never automatically reopen a previous `public_temporary` URL.

If the backup manifest contains:

```env
KX_NETWORK_PROFILE=public_temporary
KX_PUBLIC_MODE_ENABLED=true
```

the restored instance must start as:

```env
KX_NETWORK_PROFILE=local_only
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
KX_PUBLIC_MODE_EXPIRES_AT=
```

The operator may create a new temporary public URL only through the Manager UI or canonical CLI, with authentication and expiration.

## 17.5 Public VPS Restore Rule

A restored `public_vps` instance must not become public until the following checks pass:

```text
firewall_enabled
dangerous_ports_blocked
postgres_not_public
redis_not_public
docker_socket_not_mounted
admin_surface_private
ssh_restricted
root_ssh_disabled
password_ssh_disabled
backups_enabled
```

If any check fails, the instance must remain in `local_only` or `intranet_private`.

## 17.6 Rollback Network Rule

Rollback must not increase exposure.

Allowed automatic rollback transitions:

```text
public_temporary -> intranet_private
private_tunnel -> intranet_private
public_vps -> public_vps only if Security Gate PASS
any profile -> local_only
```

Forbidden automatic rollback transitions:

```text
local_only -> public_temporary
intranet_private -> public_temporary
private_tunnel -> public_temporary
any profile -> public_vps
```

## 17.7 Backup Metadata for Network Profiles

Every backup manifest must record the active network profile as metadata:

```yaml
network:
  kx_network_profile: intranet_private
  kx_exposure_mode: private
  kx_public_mode_enabled: false
  kx_public_mode_expires_at: null
```

This metadata is used to propose a restore profile, but it must not override current Security Gate policy.

## 17.8 Manager UX Requirement

During restore, the Manager must show:

```text
Backup source profile: <PROFILE_FROM_BACKUP>
Restore target profile: <SELECTED_SAFE_PROFILE>
Public exposure after restore: disabled by default
```

For `public_temporary` and `public_vps`, the Manager must require explicit confirmation before any public exposure is enabled.


---

## 18. Security Gate Integration

Before applying any profile, the Manager must call:

```bash
kx security check <INSTANCE_ID> --profile <KX_NETWORK_PROFILE>
```

The profile may be applied only if all blocking checks return `PASS`.

Canonical blocking checks:

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
```

Additional checks for `public_temporary`:

```text
public_mode_expiration_present
public_mode_auth_enabled
tunnel_provider_configured
```

Additional checks for `public_vps`:

```text
ssh_restricted
root_ssh_disabled
password_ssh_disabled
cloud_firewall_present_or_acknowledged
backups_enabled
```

---

## 19. Manager UX Contract

The user must not see raw Docker or firewall details during normal operation.

The user sees:

```text
Mode réseau:
- Local seulement
- Intranet privé
- Tunnel privé
- Public temporaire
- Public VPS
```

The user sees the result:

```text
Current mode: Intranet private
Access URL: https://konnaxion.local
Internet exposure: Disabled
Security status: OK
```

Advanced details may be available under:

```text
Security details
Network diagnostics
Logs
```

---

## 20. Agent Implementation Contract

The Konnaxion Agent is responsible for applying profile rules.

Allowed actions:

```text
create Docker networks
start/stop allowed services
bind Traefik to approved interfaces
apply local firewall rules
generate profile-specific environment files
configure tunnel provider
close expired tunnel
run Security Gate checks
write audit logs
```

Forbidden actions:

```text
run arbitrary shell commands from capsule manifest
start unknown containers
pull unsigned images
mount Docker socket into containers
enable privileged containers
bind forbidden ports
open public router ports automatically
disable firewall
```

---

## 21. Audit Log Requirements

Every profile change must create an audit event.

Canonical event fields:

```yaml
event_type: network_profile_changed
instance_id: <INSTANCE_ID>
old_profile: <OLD_PROFILE>
new_profile: <NEW_PROFILE>
exposure_mode: <KX_EXPOSURE_MODE>
public_mode_enabled: <true|false>
public_mode_expires_at: <timestamp_or_empty>
actor: <local_user_or_system>
timestamp: <ISO8601>
security_gate_result: <PASS|FAIL_BLOCKING>
```

Public temporary expiration must create:

```yaml
event_type: public_temporary_expired
instance_id: <INSTANCE_ID>
previous_profile: public_temporary
new_profile: intranet_private
timestamp: <ISO8601>
```

---

## 22. Acceptance Tests

## 22.1 `local_only`

Expected:

```text
curl -k https://localhost/ returns 200 or redirect
LAN device cannot reach Konnaxion
public internet cannot reach Konnaxion
ports 3000/5432/6379/5555 are not externally reachable
```

## 22.2 `intranet_private`

Expected:

```text
LAN device can reach https://konnaxion.local or https://<LAN_IP>
public internet cannot reach Konnaxion
router has no required port forwarding
Postgres is not reachable from LAN
Redis is not reachable from LAN
Flower is not reachable from LAN unless explicitly protected and enabled
```

## 22.3 `private_tunnel`

Expected:

```text
approved tunnel user can reach Konnaxion
non-approved user cannot reach Konnaxion
no public router port is open
dangerous ports are blocked
```

## 22.4 `public_temporary`

Expected:

```text
public demo URL works
authentication is required
expiration is set
after expiration URL no longer works
profile returns to intranet_private or local_only
dangerous ports remain blocked
```

## 22.5 `public_vps`

Expected:

```text
https://public-host/ works
https://public-host/api/ reaches Django API
https://public-host/admin/ reaches Django admin
https://public-host/media/ reaches media service
ports 3000/5555/5432/6379/8000 are not public
SSH is key-only and restricted
```

---

## 23. Non-Goals

This document does not define:

```text
Docker Compose service implementation
Capsule file format
Agent privilege model
Backup/restore archive format
Backup retention policy
Database restore procedure
GUI screen design beyond network-profile requirements
Cloud provider provisioning
Full threat model
```

Those are defined in separate documents.

---

## 24. Final Rule

Konnaxion networking must be:

```text
private by default
deny by default
Traefik-only at the edge
temporary public access only with expiration
no public database
no public Redis
no public Docker
no public Next.js direct port
no public Django direct port
```

If a profile requires exposing an internal service directly, the profile is invalid.

