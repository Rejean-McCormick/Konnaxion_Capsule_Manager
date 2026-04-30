doc_id: DOC-18
title: Konnaxion Capsule Manager GUI Target Modes Contract
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: technical-contract
owner: Konnaxion
last_updated: 2026-04-30
depends_on:
  - DOC-16_Konnaxion_Manager_GUI_Technical_Contract.md
  - DOC-17_Konnaxion_GUI_Action_Coverage_Contract.md
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
```

The GUI must not treat target mode as a cosmetic label. It must enforce the correct canonical profile, exposure mode, and deployment rules.

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

| Target mode        | Network profile    | Exposure mode      |       Public mode | Runtime location    | Purpose                                  |
| ------------------ | ------------------ | ------------------ | ----------------: | ------------------- | ---------------------------------------- |
| `local`            | `local_only`       | `private`          |                no | local machine       | Same-machine development and maintenance |
| `intranet`         | `intranet_private` | `private` or `lan` |                no | local/intranet host | Private LAN/internal use                 |
| `temporary_public` | `public_temporary` | `temporary_tunnel` | yes, time-limited | local/intranet host | Short-lived public demo                  |
| `droplet`          | `public_vps`       | `public`           |     yes, explicit | remote VPS/Droplet  | Public remote deployment                 |

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

---

## 5. Local Target

## 5.1 Purpose

Local target is for same-machine development and maintenance.

It must never expose Konnaxion to LAN, VPN, tunnel, or public traffic.

## 5.2 Required values

```text
target_mode = local
network_profile = local_only
exposure_mode = private
public_mode_enabled = false
public_mode_expires_at = null
```

## 5.3 Required paths

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

## 5.4 Required GUI fields

```text
Konnaxion source folder
Capsule output folder
Instance ID
Capsule ID
Capsule version
```

## 5.5 Allowed GUI actions

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

## 5.6 Forbidden in local target

```text
public_vps
public_temporary
temporary_tunnel
public exposure
droplet SSH fields
domain requirement
```

---

## 6. Intranet Target

## 6.1 Purpose

Intranet target is for private LAN/internal use.

It may be reachable from other machines on the same trusted network only if the selected exposure mode is `lan`.

## 6.2 Required values

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

## 6.3 Required GUI fields

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

## 6.4 Allowed GUI actions

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

## 6.5 Forbidden in intranet target

```text
public_vps
public_temporary without changing target mode
temporary_tunnel
public exposure
droplet SSH fields
```

## 6.6 Safety rule

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

## 7.1 Purpose

Temporary public target is for short-lived demos or support access.

It must have an expiration.

It must never be default.

## 7.2 Required values

```text
target_mode = temporary_public
network_profile = public_temporary
exposure_mode = temporary_tunnel
public_mode_enabled = true
public_mode_expires_at = required
```

## 7.3 Required GUI fields

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

## 7.4 Required expiration

`public_mode_expires_at` must be an ISO-8601 datetime.

Example:

```text
2026-04-30T22:00:00Z
```

The GUI must reject temporary public target if expiration is missing.

## 7.5 Allowed GUI actions

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

## 7.6 Required warnings

The GUI must show:

```text
Temporary public exposure is enabled.
An expiration is required.
Internal services remain private.
Disable public mode when the demo is complete.
```

## 7.7 Safety gates

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

## 8.1 Purpose

Droplet target is for remote VPS deployment.

It uses the canonical public VPS network profile.

## 8.2 Required values

```text
target_mode = droplet
network_profile = public_vps
exposure_mode = public
public_mode_enabled = true
public_mode_expires_at = null
remote_kx_root = /opt/konnaxion
```

## 8.3 Required GUI fields

```text
Droplet name
Droplet host/IP
SSH user
SSH key path
Remote KX_ROOT
Remote capsule directory
Domain or public host
Instance ID
Capsule file
Confirmation checkbox
```

Recommended defaults:

```text
droplet_user = root
remote_kx_root = /opt/konnaxion
remote_capsule_dir = /opt/konnaxion/capsules
```

## 8.4 Optional GUI fields

```text
Remote Agent URL
SSH port
Known hosts file
Domain
Email for TLS
Firewall profile
```

## 8.5 Required Droplet variables

| Variable                 | Example                                     |
| ------------------------ | ------------------------------------------- |
| `KX_DROPLET_NAME`        | `konnaxion-prod-01`                         |
| `KX_DROPLET_HOST`        | `203.0.113.10`                              |
| `KX_DROPLET_USER`        | `root`                                      |
| `KX_DROPLET_SSH_KEY`     | `C:\Users\user\.ssh\id_ed25519`             |
| `KX_DROPLET_KX_ROOT`     | `/opt/konnaxion`                            |
| `KX_DROPLET_CAPSULE_DIR` | `/opt/konnaxion/capsules`                   |
| `KX_DROPLET_DOMAIN`      | `app.example.com`                           |
| `KX_DROPLET_AGENT_URL`   | `http://203.0.113.10:8765/v1` or tunnel URL |

## 8.6 Allowed GUI actions

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

## 8.7 Droplet deploy flow

Droplet deployment must follow this order:

```text
validate target config
build capsule locally if requested
verify capsule locally
copy capsule to remote capsule directory
ensure remote runtime directories exist
check remote Agent or bootstrap approved remote runtime
import capsule remotely
create or update remote instance
set public_vps profile
run Security Gate
start remote instance
check remote health
show public URL
```

## 8.8 Droplet safety gates

Droplet deployment must be blocked unless:

```text
droplet_host is set
droplet_user is set
ssh_key_path exists
remote_kx_root is set
remote_capsule_dir is under remote_kx_root
network_profile = public_vps
exposure_mode = public
confirmation is accepted
```

## 8.9 Forbidden Droplet behavior

```text
password embedded in command
shell=True with untrusted input
arbitrary remote command text
copying capsule outside remote capsule dir
using non-canonical network profile
using public exposure without confirmation
exposing internal service ports directly
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
    domain: str | None = None
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
public_vps requires confirmation
droplet requires host, user, ssh key, remote root
remote capsule dir must be under remote root
local/intranet must not include droplet SSH fields
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

## 11.1 LocalTargetForm

Fields:

```text
target_mode
instance_id
runtime_root
capsule_output_dir
source_dir
```

## 11.2 IntranetTargetForm

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

## 11.3 TemporaryPublicTargetForm

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

## 11.4 DropletTargetForm

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
confirmed = true
```

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

---

## 13. Deployment Result Contract

Every deployment action must return normalized result data.

## 13.1 Local deployment result

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
    "url": "http://127.0.0.1"
  }
}
```

## 13.2 Intranet deployment result

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

## 13.3 Temporary public deployment result

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

## 13.4 Droplet deployment result

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
    "remote_kx_root": "/opt/konnaxion",
    "remote_capsule_path": "/opt/konnaxion/capsules/konnaxion-v14-demo-2026.04.30.kxcap",
    "public_url": "https://app.example.com",
    "agent_health_url": "http://203.0.113.10:8765/v1/health"
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
```

Required target mode tests:

```text
test_target_mode_enum_values
test_local_target_maps_to_local_only_private
test_intranet_target_maps_to_intranet_private_private
test_intranet_target_allows_lan
test_temporary_public_maps_to_public_temporary_temporary_tunnel
test_temporary_public_requires_expiration
test_temporary_public_requires_confirmation
test_droplet_maps_to_public_vps_public
test_droplet_requires_host
test_droplet_requires_user
test_droplet_requires_ssh_key
test_droplet_requires_remote_root
test_droplet_remote_capsule_dir_must_be_under_remote_root
test_local_target_rejects_droplet_fields
test_intranet_target_rejects_public_exposure
test_invalid_target_mode_rejected
```

Run:

```powershell
uv run python -m compileall kx_manager/ui kx_manager/services tests
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
Temporary public mode cannot run without expiration.
pytest passes.
```

The GUI target modes are production-safe when:

```text
No target mode executes arbitrary commands.
No target mode exposes internal service ports.
Public modes require explicit confirmation.
Temporary public mode has expiration.
Droplet mode uses validated host/user/key/root/capsule path.
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

The selected target mode must determine the allowed profile and exposure options.


