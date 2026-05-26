doc_id: DOC-18
title: Konnaxion Capsule Manager GUI Target Modes Contract
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: technical-contract
owner: Konnaxion
last_updated: 2026-05-03
depends_on:
  - DOC-16_Konnaxion_Manager_GUI_Technical_Contract.md
  - DOC-17_Konnaxion_GUI_Action_Coverage_Contract.md
  - DOC-17A_Konnaxion_GUI_Action_Payload_Contract.md
  - DOC-19_Konnaxion_GUI_Page_Split_Droplet_Payload_Contract.md
---

# DOC-18 — Konnaxion Capsule Manager GUI Target Modes Contract

## 1. Purpose

This document defines the GUI target modes used by the Konnaxion Capsule Manager.

Target modes answer this operator question:

```text
Where do I want this capsule to run?
````

The GUI must support:

```text
local same-machine development
private intranet deployment
temporary public demo exposure
remote Droplet/VPS deployment
```

Target mode selection must drive:

```text
network_profile
exposure_mode
runtime root
capsule output path
deployment flow
required form fields
safety gates
confirmation requirements
Agent transport mode
public host/domain propagation
runtime env generation
Traefik routing generation
```

The GUI must not treat target mode as a cosmetic label. It must enforce the correct canonical profile, exposure mode, deployment rules, host rules, and Agent transport.

---

## 2. Target Mode Values

`kx_manager/services/targets.py` must own target-mode validation.

Canonical target mode values:

```text
local
intranet
temporary_public
droplet
```

Recommended enum:

```python
class TargetMode(StrEnum):
    LOCAL = "local"
    INTRANET = "intranet"
    TEMPORARY_PUBLIC = "temporary_public"
    DROPLET = "droplet"
```

Do not use alternate values such as:

```text
dev
demo
lan_private
vps
server
production
cloud
public_server
```

Those may be display labels, not stored values.

---

## 3. Target Mode Matrix

| Target mode        | Network profile    | Exposure mode      | Public mode       | Runtime location    | Agent transport | Purpose                                  |
| ------------------ | ------------------ | ------------------ | ----------------- | ------------------- | --------------- | ---------------------------------------- |
| `local`            | `local_only`       | `private`          | no                | local machine       | local HTTP      | Same-machine development and maintenance |
| `intranet`         | `intranet_private` | `private` or `lan` | no                | local/intranet host | local HTTP      | Private LAN/internal use                 |
| `temporary_public` | `public_temporary` | `temporary_tunnel` | yes, time-limited | local/intranet host | local HTTP      | Short-lived public demo                  |
| `droplet`          | `public_vps`       | `public`           | yes, explicit     | remote VPS/Droplet  | SSH-local Agent | Public remote deployment                 |

Default target mode:

```text
intranet
```

Default profile/exposure:

```text
network_profile = intranet_private
exposure_mode = private
```

---

## 4. Canonical Target Variables

The GUI must use these variables consistently.

| Variable                 | Meaning                                               |
| ------------------------ | ----------------------------------------------------- |
| `KX_TARGET_MODE`         | `local`, `intranet`, `temporary_public`, or `droplet` |
| `KX_TARGET_PROFILE`      | Canonical `NetworkProfile` value                      |
| `KX_TARGET_EXPOSURE`     | Canonical `ExposureMode` value                        |
| `KX_TARGET_NAME`         | Human-readable target name                            |
| `KX_TARGET_HOST`         | Target host/IP/domain where applicable                |
| `KX_TARGET_RUNTIME_ROOT` | Runtime root on the selected target                   |
| `KX_TARGET_CAPSULE_DIR`  | Capsule folder on selected target                     |
| `KX_TARGET_INSTANCE_ID`  | Instance ID to create/update/start                    |
| `KX_TARGET_PUBLIC_URL`   | Public URL when applicable                            |
| `KX_TARGET_PRIVATE_URL`  | Private/local URL when applicable                     |

For public target modes, the GUI must resolve one canonical public host.

Canonical public host precedence:

```text
domain
droplet_domain
public_host
host
droplet_host
```

The Manager may store `domain`, but Agent network APIs must receive the canonical value as:

```text
host
```

The Manager must not send `domain` to `/v1/network/set-profile` unless the Agent schema explicitly supports it.

---

## 5. Local Target

### 5.1 Purpose

Local target is for same-machine development and maintenance.

It must never expose Konnaxion to LAN, VPN, tunnel, or public traffic.

### 5.2 Required values

```text
target_mode = local
network_profile = local_only
exposure_mode = private
public_mode_enabled = false
public_mode_expires_at = null
```

### 5.3 Required paths

Windows development defaults:

```text
KX_ROOT = C:\mycode\Konnaxion\runtime
KX_CAPSULE_OUTPUT_DIR = C:\mycode\Konnaxion\runtime\capsules
```

Canonical runtime layout:

```text
runtime/
  capsules/
  instances/
  backups/
  shared/
```

### 5.4 Required GUI fields

```text
Konnaxion source folder
Capsule output folder
Instance ID
Capsule ID
Capsule version
```

### 5.5 Allowed GUI actions

```text
build_capsule
rebuild_capsule
verify_capsule
import_capsule
create_instance
update_instance
start_instance
stop_instance
restart_instance
instance_status
view_health
view_logs
run_security_check
create_backup
restore_backup
rollback_instance
deploy_local
```

### 5.6 Forbidden in local target

```text
public_vps
public_temporary
temporary_tunnel
public exposure
droplet SSH fields
domain requirement
remote_agent_url
SSH-local transport
```

---

## 6. Intranet Target

### 6.1 Purpose

Intranet target is for private LAN/internal use.

It may be reachable from other machines on the same trusted network only if the selected exposure mode is `lan`.

### 6.2 Required values

Default intranet:

```text
target_mode = intranet
network_profile = intranet_private
exposure_mode = private
public_mode_enabled = false
public_mode_expires_at = null
```

Optional LAN exposure:

```text
target_mode = intranet
network_profile = intranet_private
exposure_mode = lan
public_mode_enabled = false
public_mode_expires_at = null
```

### 6.3 Required GUI fields

```text
Konnaxion source folder
Capsule output folder
Instance ID
Capsule ID
Capsule version
Private host/domain
```

Example private hosts:

```text
konnaxion.local
konnaxion.lan
192.168.1.50
```

### 6.4 Allowed GUI actions

```text
build_capsule
rebuild_capsule
verify_capsule
import_capsule
create_instance
update_instance
set_network_profile
start_instance
stop_instance
restart_instance
instance_status
view_health
view_logs
run_security_check
create_backup
restore_backup
rollback_instance
deploy_intranet
```

### 6.5 Forbidden in intranet target

```text
public_vps
public_temporary without changing target mode
temporary_tunnel
public exposure
droplet SSH fields
remote_agent_url
SSH-local transport
```

### 6.6 Safety rule

Internal services must never be directly exposed.

Only the intended public/private entrypoint may be reachable.

Forbidden direct service exposure:

```text
frontend-next
django-api
postgres
redis
celeryworker
celerybeat
flower
media-nginx
kx-agent
```

---

## 7. Temporary Public Target

### 7.1 Purpose

Temporary public target is for short-lived demos or support access.

It must have an expiration.

It must never be default.

### 7.2 Required values

```text
target_mode = temporary_public
network_profile = public_temporary
exposure_mode = temporary_tunnel
public_mode_enabled = true
public_mode_expires_at = required
```

### 7.3 Required GUI fields

```text
Konnaxion source folder
Capsule output folder
Instance ID
Capsule ID
Capsule version
Generated or configured public host
Public mode expiration
Confirmation checkbox
```

### 7.4 Required expiration

`public_mode_expires_at` must be an ISO-8601 datetime.

Example:

```text
2026-04-30T22:00:00Z
```

The GUI must reject temporary public target if expiration is missing.

### 7.5 Allowed GUI actions

```text
build_capsule
rebuild_capsule
verify_capsule
import_capsule
create_instance
update_instance
set_network_profile
disable_public_mode
start_instance
stop_instance
restart_instance
instance_status
view_health
view_logs
run_security_check
create_backup
rollback_instance
set_target_temporary_public
```

### 7.6 Required warnings

The GUI must show:

```text
Temporary public exposure is enabled.
An expiration is required.
Internal services remain private.
Disable public mode when the demo is complete.
```

### 7.7 Safety gates

Before applying this target:

```text
public_mode_expires_at must be present
exposure_mode must be temporary_tunnel
network_profile must be public_temporary
confirmation must be accepted
Security Gate must run before start
```

---

## 8. Droplet Target

### 8.1 Purpose

Droplet target is for remote VPS deployment.

It uses the canonical public VPS network profile.

The Droplet Agent should remain private on the Droplet loopback interface:

```text
127.0.0.1:8765
```

The Manager must reach the private Agent through SSH-local curl:

```text
Manager on Windows
  -> ssh root@droplet_host
    -> curl http://127.0.0.1:8765/v1/... on the Droplet
```

The GUI must not require a temporary SSH tunnel for Droplet deployment.

### 8.2 Required values

```text
target_mode = droplet
network_profile = public_vps
exposure_mode = public
public_mode_enabled = true
public_mode_expires_at = null
remote_kx_root = /opt/konnaxion
```

### 8.3 Required GUI fields

```text
Droplet name
Droplet host/IP
SSH user
SSH key path
Remote KX_ROOT
Remote capsule directory
Domain
Instance ID
Capsule file
Confirmation checkbox
```

Recommended defaults:

```text
droplet_user = root
remote_kx_root = /opt/konnaxion
remote_capsule_dir = /opt/konnaxion/capsules
ssh_port = 22
remote_agent_url = blank
```

### 8.4 Optional GUI fields

```text
Remote Agent URL
SSH port
Known hosts file
Email for TLS
Firewall profile
```

`Remote Agent URL` is optional and should normally be blank.

Blank, loopback, stale tunnel, or mismatched Agent URLs must resolve to SSH-local transport.

Examples that must use SSH-local transport in Droplet mode:

```text
empty remote_agent_url
http://127.0.0.1:18765/v1
http://localhost:18765/v1
http://203.0.113.10:8765/v1
remote_agent_url host does not match selected droplet_host
```

A direct `remote_agent_url` may be used only when it is explicitly configured, non-loopback, and points to the selected Droplet host.

### 8.5 Required Droplet variables

| Variable                 | Example                         |
| ------------------------ | ------------------------------- |
| `KX_DROPLET_NAME`        | `konnaxion-prod-01`             |
| `KX_DROPLET_HOST`        | `203.0.113.10`                  |
| `KX_DROPLET_USER`        | `root`                          |
| `KX_DROPLET_SSH_KEY`     | `C:\Users\user\.ssh\id_ed25519` |
| `KX_DROPLET_KX_ROOT`     | `/opt/konnaxion`                |
| `KX_DROPLET_CAPSULE_DIR` | `/opt/konnaxion/capsules`       |
| `KX_DROPLET_DOMAIN`      | `app.example.com`               |
| `KX_DROPLET_AGENT_URL`   | blank by default                |

### 8.6 Canonical Droplet public host

For Droplet mode, the Manager must resolve:

```text
canonical_public_host = domain or droplet_domain or public_host or droplet_host
```

The Agent `/v1/network/set-profile` request must receive:

```json
{
  "instance_id": "demo-001",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "host": "app.example.com",
  "public_mode_enabled": true,
  "public_mode_expires_at": null
}
```

The Manager must not send this to the Agent network endpoint:

```json
{
  "domain": "app.example.com"
}
```

unless the Agent schema explicitly supports `domain`.

### 8.7 Required generated runtime values

For Droplet/public VPS runtime, the Agent must generate or update:

```text
KX_HOST=<canonical_public_host>
KX_NETWORK_PROFILE=public_vps
KX_EXPOSURE_MODE=public
KX_PUBLIC_MODE_ENABLED=true
```

Django env must include:

```text
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,<canonical_public_host>,django-api,kx-<instance_id>-django-api
DJANGO_CSRF_TRUSTED_ORIGINS=https://<canonical_public_host>,http://<canonical_public_host>
```

Frontend env must include:

```text
NEXT_PUBLIC_API_BASE=https://<canonical_public_host>/api
NEXT_PUBLIC_BACKEND_BASE=https://<canonical_public_host>
```

The generated public VPS runtime must not leave these values set to loopback:

```text
KX_HOST=127.0.0.1
DJANGO_ALLOWED_HOSTS=127.0.0.1 only
NEXT_PUBLIC_API_BASE=https://127.0.0.1/api
NEXT_PUBLIC_BACKEND_BASE=https://127.0.0.1
Traefik Host(`127.0.0.1`)
```

### 8.8 Traefik routing contract

Droplet/public VPS runtime must route through Traefik on ports 80 and 443 only.

The runtime may use Traefik file provider or labels, but file provider is preferred because it does not require mounting the Docker socket.

Preferred Traefik dynamic config:

```yaml
http:
  routers:
    kx-frontend:
      rule: "Host(`app.example.com`) && PathPrefix(`/`)"
      entryPoints:
        - websecure
      tls: {}
      service: kx-frontend
      priority: 1

    kx-api:
      rule: "Host(`app.example.com`) && PathPrefix(`/api/`)"
      entryPoints:
        - websecure
      tls: {}
      service: kx-api
      priority: 100

    kx-admin:
      rule: "Host(`app.example.com`) && PathPrefix(`/admin/`)"
      entryPoints:
        - websecure
      tls: {}
      service: kx-api
      priority: 100

  services:
    kx-frontend:
      loadBalancer:
        servers:
          - url: "http://kx-demo-001-frontend-next:3000"

    kx-api:
      loadBalancer:
        servers:
          - url: "http://kx-demo-001-django-api:5000"
```

The generated Traefik runtime must not depend on Docker labels unless the Docker provider is configured and allowed.

The generated Traefik runtime must not mount:

```text
/var/run/docker.sock
/run/docker.sock
```

unless explicitly approved by the Security Gate.

### 8.9 Healthcheck contract

Django healthchecks must not depend on `wget`, `curl`, public DNS, Host header, or `/api/health/`.

Required robust Django healthcheck:

```text
python -c "import socket; sock=socket.create_connection(('127.0.0.1',5000),5); sock.close()"
```

Forbidden Django healthcheck fragments:

```text
wget
curl
/api/health/
"api/health"
Host header dependency
```

`media-nginx` must not use `wget` unless the selected image includes it. If no reliable built-in probe exists, either use an available tool or omit the healthcheck for stock `nginx:stable`.

### 8.10 Frontend runtime contract

The frontend image/runtime must not require network access at container start.

Forbidden runtime command:

```text
pnpm start
corepack
```

Required runtime behavior:

```text
node node_modules/next/dist/bin/next start -H 0.0.0.0 -p 3000
```

The frontend runtime image must include:

```text
package.json
node_modules
.next
public
next.config.*
env.mjs
```

### 8.11 Capsule image archive contract

Droplet deployments must not rely on images already existing on the VPS.

A deployable `.kxcap` must include required image archives:

```text
images/frontend-next.oci.tar
images/django-api.oci.tar
images/traefik.oci.tar
images/media-nginx.oci.tar
```

Builder verification must fail if:

```text
images/ contains only README.json
required images/*.oci.tar are missing
required image archives are not listed in checksums.txt
manifest references image archives that are missing
```

The GUI must not show “Capsule verified” as success if the capsule cannot start on a clean Droplet because required runtime images are absent.

### 8.12 Allowed GUI actions

```text
build_capsule
rebuild_capsule
verify_capsule
copy_capsule_to_droplet
check_droplet_agent
import_capsule
create_instance
update_instance
set_network_profile
start_droplet_instance
instance_status
view_health
view_logs
run_security_check
create_backup
rollback_instance
deploy_droplet
```

### 8.13 Droplet deploy flow

Droplet deployment must follow this order:

```text
validate target config
build capsule locally if requested
verify capsule locally, including required image archives
copy capsule to remote capsule directory
ensure remote runtime directories exist
check private Droplet Agent through SSH-local curl
probe Agent contract/capabilities when available
import capsule remotely through SSH-local Agent API
create or update remote instance through SSH-local Agent API
set public_vps profile through SSH-local Agent API
run Security Gate through SSH-local Agent API
start remote instance through SSH-local Agent API
check remote health
show public URL
```

### 8.14 Droplet safety gates

Droplet deployment must be blocked unless:

```text
droplet_host is set
droplet_user is set
ssh_key_path exists
remote_kx_root is set
remote_capsule_dir is under remote_kx_root
domain is set
network_profile = public_vps
exposure_mode = public
confirmation is accepted
capsule verifies successfully
capsule includes required image archives
```

### 8.15 Forbidden Droplet behavior

```text
password embedded in command
shell=True with untrusted input
arbitrary remote command text from the GUI
copying capsule outside remote capsule dir
using non-canonical network profile
using public exposure without confirmation
exposing internal service ports directly
requiring a temporary SSH tunnel for normal Droplet deploy
calling http://127.0.0.1:18765/v1 from Manager as if it were the Droplet
binding the Agent publicly on 0.0.0.0:8765
using Docker socket mounts for Traefik routing by default
silently falling back to 127.0.0.1 for public_vps host config
```

---

## 9. Target Configuration Model

Create in:

```text
kx_manager/services/targets.py
```

Recommended models:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from kx_shared.konnaxion_constants import ExposureMode, NetworkProfile


class TargetMode(StrEnum):
    LOCAL = "local"
    INTRANET = "intranet"
    TEMPORARY_PUBLIC = "temporary_public"
    DROPLET = "droplet"


@dataclass(frozen=True, slots=True)
class TargetConfig:
    target_mode: TargetMode
    network_profile: NetworkProfile
    exposure_mode: ExposureMode
    instance_id: str
    runtime_root: str
    capsule_dir: str
    host: str | None = None
    public_mode_expires_at: str | None = None
    confirmed: bool = False


@dataclass(frozen=True, slots=True)
class DropletTargetConfig(TargetConfig):
    droplet_name: str = ""
    droplet_host: str = ""
    droplet_user: str = "root"
    ssh_key_path: Path | None = None
    remote_kx_root: str = "/opt/konnaxion"
    remote_capsule_dir: str = "/opt/konnaxion/capsules"
    domain: str = ""
    remote_agent_url: str | None = None
    ssh_port: int = 22
```

---

## 10. Target Validation Rules

Required validation function:

```python
def validate_target_config(config: TargetConfig) -> None:
    ...
```

Validation rules:

```text
target_mode must be canonical
network_profile must match target_mode
exposure_mode must be allowed for network_profile
temporary_public requires public_mode_expires_at
temporary_public requires confirmation
public_vps requires confirmation
droplet requires host, user, ssh key, remote root, remote capsule dir, and domain
remote capsule dir must be under remote root
local/intranet must not include droplet SSH fields
public_vps must not use 127.0.0.1 as canonical host
remote_agent_url blank/loopback/stale values must resolve to SSH-local transport
```

Profile mapping:

```python
TARGET_PROFILE_MAP = {
    TargetMode.LOCAL: NetworkProfile.LOCAL_ONLY,
    TargetMode.INTRANET: NetworkProfile.INTRANET_PRIVATE,
    TargetMode.TEMPORARY_PUBLIC: NetworkProfile.PUBLIC_TEMPORARY,
    TargetMode.DROPLET: NetworkProfile.PUBLIC_VPS,
}
```

Exposure mapping:

```python
TARGET_DEFAULT_EXPOSURE_MAP = {
    TargetMode.LOCAL: ExposureMode.PRIVATE,
    TargetMode.INTRANET: ExposureMode.PRIVATE,
    TargetMode.TEMPORARY_PUBLIC: ExposureMode.TEMPORARY_TUNNEL,
    TargetMode.DROPLET: ExposureMode.PUBLIC,
}
```

---

## 11. GUI Form Contract

`kx_manager/ui/forms.py` must expose forms for target modes.

Required forms:

```text
TargetModeForm
LocalTargetForm
IntranetTargetForm
TemporaryPublicTargetForm
DropletTargetForm
DeployLocalForm
DeployIntranetForm
DeployDropletForm
```

### 11.1 LocalTargetForm

Fields:

```text
target_mode
instance_id
runtime_root
capsule_output_dir
source_dir
```

### 11.2 IntranetTargetForm

Fields:

```text
target_mode
instance_id
runtime_root
capsule_output_dir
source_dir
host
exposure_mode
```

Allowed exposure modes:

```text
private
lan
```

### 11.3 TemporaryPublicTargetForm

Fields:

```text
target_mode
instance_id
runtime_root
capsule_output_dir
source_dir
public_host
public_mode_expires_at
confirmed
```

Required:

```text
public_mode_expires_at
confirmed = true
```

### 11.4 DropletTargetForm

Fields:

```text
target_mode
instance_id
source_dir
capsule_file
droplet_name
droplet_host
droplet_user
ssh_key_path
ssh_port
remote_kx_root
remote_capsule_dir
domain
remote_agent_url
confirmed
```

Required:

```text
droplet_host
droplet_user
ssh_key_path
remote_kx_root
remote_capsule_dir
domain
confirmed = true
```

Droplet form normalization:

```text
domain -> canonical public host
remote_agent_url blank/loopback/mismatched -> SSH-local Agent transport
```

The UI should display `remote_agent_url` as advanced/optional.

---

## 12. Target Page UI Contract

`GET /ui/targets` must render:

```text
Target mode selector
Local target card
Intranet target card
Temporary public target card
Droplet target card
Current target summary
Validation messages
Deploy buttons
Agent transport summary
Public host summary
```

Required buttons:

```text
Set Local Target
Set Intranet Target
Set Temporary Public Target
Set Droplet Target
Deploy Local
Deploy Intranet
Deploy Droplet
Check Droplet Agent
Copy Capsule to Droplet
Start Droplet Instance
```

For Droplet target, the UI must show:

```text
Agent transport: ssh
Agent health URL: http://127.0.0.1:8765/v1/health on Droplet
Public URL: https://<domain>
```

when `remote_agent_url` is blank, loopback, stale, or ignored.

---

## 13. Deployment Result Contract

Every deployment action must return normalized result data.

### 13.1 Local deployment result

```json
{
  "ok": true,
  "action": "deploy_local",
  "instance_id": "demo-001",
  "message": "Local deployment completed.",
  "data": {
    "target_mode": "local",
    "network_profile": "local_only",
    "exposure_mode": "private",
    "capsule_file": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",
    "url": "https://127.0.0.1"
  }
}
```

### 13.2 Intranet deployment result

```json
{
  "ok": true,
  "action": "deploy_intranet",
  "instance_id": "demo-001",
  "message": "Intranet deployment completed.",
  "data": {
    "target_mode": "intranet",
    "network_profile": "intranet_private",
    "exposure_mode": "private",
    "capsule_file": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",
    "url": "https://konnaxion.local"
  }
}
```

### 13.3 Temporary public deployment result

```json
{
  "ok": true,
  "action": "set_target_temporary_public",
  "instance_id": "demo-001",
  "message": "Temporary public target configured.",
  "data": {
    "target_mode": "temporary_public",
    "network_profile": "public_temporary",
    "exposure_mode": "temporary_tunnel",
    "public_mode_expires_at": "2026-04-30T22:00:00Z",
    "public_url": "https://generated-demo.example"
  }
}
```

### 13.4 Droplet deployment result

```json
{
  "ok": true,
  "action": "deploy_droplet",
  "instance_id": "demo-001",
  "message": "Droplet deployment completed.",
  "data": {
    "target_mode": "droplet",
    "network_profile": "public_vps",
    "exposure_mode": "public",
    "droplet_host": "203.0.113.10",
    "domain": "app.example.com",
    "host": "app.example.com",
    "remote_kx_root": "/opt/konnaxion",
    "remote_capsule_path": "/opt/konnaxion/capsules/konnaxion-v14-demo-2026.04.30.kxcap",
    "public_url": "https://app.example.com",
    "remote_agent_url": "",
    "agent_health_url": "http://127.0.0.1:8765/v1/health",
    "agent_transport": "ssh"
  }
}
```

### 13.5 Stale remote Agent result

If the Agent rejects current schema fields such as `host`, `public_mode_enabled`, `verify`, `overwrite`, or `capsule_id`, the GUI must show a clear bootstrap-required result.

```json
{
  "ok": false,
  "action": "deploy_droplet",
  "instance_id": "demo-001",
  "message": "Remote Droplet Agent is stale. Run Bootstrap Droplet Agent, then rerun Deploy Droplet.",
  "data": {
    "required_action": "bootstrap_droplet_agent",
    "stale_remote_agent_schema": true,
    "agent_transport": "ssh"
  }
}
```

---

## 14. Required Tests

Create or update:

```text
tests/test_manager_ui_forms.py
tests/test_manager_ui_action_coverage.py
tests/test_manager_ui_target_modes.py
tests/test_compose_generation.py
tests/test_capsule_verify.py
```

Required target mode tests:

```text
test_target_mode_enum_values
test_local_target_maps_to_local_only_private
test_intranet_target_maps_to_intranet_private_private
test_intranet_target_allows_lan
test_temporary_public_maps_to_public_temporary_tunnel
test_temporary_public_requires_expiration
test_temporary_public_requires_confirmation
test_droplet_maps_to_public_vps_public
test_droplet_requires_host
test_droplet_requires_user
test_droplet_requires_ssh_key
test_droplet_requires_remote_root
test_droplet_requires_domain
test_droplet_remote_capsule_dir_must_be_under_remote_root
test_local_target_rejects_droplet_fields
test_intranet_target_rejects_public_exposure
test_invalid_target_mode_rejected
```

Required Droplet transport tests:

```text
test_droplet_blank_remote_agent_url_uses_ssh_transport
test_droplet_loopback_remote_agent_url_uses_ssh_transport
test_droplet_tunnel_remote_agent_url_uses_ssh_transport
test_droplet_mismatched_remote_agent_url_uses_ssh_transport
test_droplet_direct_remote_agent_url_allowed_only_when_matching_host
test_droplet_network_payload_sends_host_not_domain
```

Required runtime generation tests:

```text
test_public_vps_requires_host
test_public_vps_uses_public_host_not_loopback
test_public_vps_traefik_file_provider_is_enabled
test_public_vps_traefik_routes_use_public_host
test_public_vps_frontend_environment_uses_public_backend_urls
test_public_vps_django_environment_allows_public_host
test_django_healthcheck_uses_socket_probe_not_wget_or_host_header
test_media_nginx_healthcheck_does_not_require_wget
test_frontend_command_does_not_require_runtime_pnpm_or_corepack
```

Required capsule verification tests:

```text
test_minimal_capsule_fixture_has_required_image_archives
test_build_checksum_entries_includes_required_image_archives
test_verify_capsule_checksums_detects_missing_image_archive
test_builder_verify_rejects_capsule_with_no_image_archives
test_builder_verify_rejects_capsule_missing_one_required_image_archive
test_builder_verify_rejects_image_archive_not_listed_in_checksums
```

Run:

```powershell
uv run python -m compileall kx_manager/ui kx_manager/services kx_agent kx_builder tests
uv run pytest -q
```

---

## 15. Acceptance Criteria

Target mode implementation is complete when:

```text
The GUI exposes /ui/targets.
The GUI can store/select local target.
The GUI can store/select intranet target.
The GUI can store/select temporary public target with expiration.
The GUI can store/select droplet target with SSH/host/domain fields.
Each target maps to canonical NetworkProfile and ExposureMode.
Invalid target/profile/exposure combinations are rejected.
Droplet deploy cannot run without required fields.
Droplet deploy uses SSH-local Agent transport by default.
Temporary public mode cannot run without expiration.
public_vps runtime uses the public host, not 127.0.0.1.
public_vps runtime generates correct Django allowed hosts.
public_vps runtime generates correct frontend public backend URLs.
public_vps runtime generates correct Traefik Host rules.
Django healthcheck does not depend on wget/curl/public Host header.
Capsule verification fails when required images/*.oci.tar are missing.
pytest passes.
```

The GUI target modes are production-safe when:

```text
No target mode executes arbitrary commands.
No target mode exposes internal service ports.
Public modes require explicit confirmation.
Temporary public mode has expiration.
Droplet mode uses validated host/user/key/root/capsule path/domain.
Droplet mode keeps the Agent private by default.
Droplet mode does not require temporary tunnels.
All deployment results are normalized and rendered safely.
```

---

## 16. Final Rule

Target mode must be the single source of deployment intent.

The GUI must never allow this drift:

```text
target_mode = intranet
network_profile = public_vps
exposure_mode = public
```

or:

```text
target_mode = droplet
network_profile = intranet_private
exposure_mode = private
```

or:

```text
target_mode = droplet
network_profile = public_vps
exposure_mode = public
KX_HOST = 127.0.0.1
```

or:

```text
target_mode = droplet
Agent transport = http to 127.0.0.1:18765 on Manager
```

The selected target mode must determine the allowed profile, exposure options, public host propagation, Agent transport, runtime env, routing, and verification requirements.


