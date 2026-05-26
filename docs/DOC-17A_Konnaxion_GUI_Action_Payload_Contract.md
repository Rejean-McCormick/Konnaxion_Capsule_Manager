doc_id: DOC-17A
title: Konnaxion GUI Action Payload Contract
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: technical-contract
owner: Konnaxion
last_updated: 2026-05-02
depends_on:
  - DOC-16_Konnaxion_Manager_GUI_Technical_Contract.md
  - DOC-17_Konnaxion_GUI_Action_Coverage_Contract.md
  - DOC-17B_Konnaxion_GUI_Action_UI_Test_Contract.md
  - DOC-18_Konnaxion_GUI_Target_Modes.md
---

# DOC-17A — Konnaxion GUI Action Payload Contract

## 1. Purpose

This document defines the canonical request payloads, normalization rules, target-mode gates, Droplet operation payloads, and payload validation expectations for the Konnaxion Capsule Manager GUI.

This contract exists so every GUI action submits a safe, complete, deterministic payload to the Manager action dispatcher.

The GUI must never allow a Droplet operation to inherit local, intranet, private, or temporary-public defaults.

---

## 2. Global Payload Rules

Every GUI action payload must include:

```text
action
````

Every instance-scoped operation must include:

```text
instance_id
```

Every target/deploy operation must include:

```text
target_mode
network_profile
exposure_mode
```

Boolean values may arrive from HTML forms as strings. Payload validation must normalize:

```text
"true", "1", "yes", "on"  -> true
"false", "0", "no", "off" -> false
```

Empty strings must be treated as absent unless the field explicitly allows an empty value.

Sensitive values such as SSH key paths may be accepted and displayed, but secret values, passwords, tokens, private keys, and generated credentials must be redacted in logs and UI results.

---

## 3. Required Request Payloads

### 3.1 Set Local Target

```json
{
  "action": "set_target_local",
  "target_mode": "local",
  "network_profile": "local_only",
  "exposure_mode": "private",
  "instance_id": "demo-001",
  "runtime_root": "C:\\mycode\\Konnaxion\\runtime",
  "capsule_dir": "C:\\mycode\\Konnaxion\\runtime\\capsules"
}
```

`set_target_local` must reject Droplet fields.

It must not submit:

```text
droplet_host
droplet_user
ssh_key_path
remote_kx_root
remote_capsule_dir
domain
droplet_domain
remote_agent_url
```

---

### 3.2 Set Intranet Target

```json
{
  "action": "set_target_intranet",
  "target_mode": "intranet",
  "network_profile": "intranet_private",
  "exposure_mode": "private",
  "instance_id": "demo-001",
  "host": "konnaxion.local",
  "runtime_root": "C:\\mycode\\Konnaxion\\runtime",
  "capsule_dir": "C:\\mycode\\Konnaxion\\runtime\\capsules"
}
```

Allowed exposure values:

```text
private
lan
```

`set_target_intranet` must reject Droplet fields.

---

### 3.3 Set Temporary Public Target

```json
{
  "action": "set_target_temporary_public",
  "target_mode": "temporary_public",
  "network_profile": "public_temporary",
  "exposure_mode": "temporary_tunnel",
  "public_mode_enabled": true,
  "public_mode_expires_at": "2026-05-02T23:59:00-04:00",
  "instance_id": "demo-001",
  "confirmed": true
}
```

`temporary_public` requires:

```text
public_mode_expires_at
confirmed = true
```

It must not be accepted without an expiration.

---

### 3.4 Set Droplet Target

```json
{
  "action": "set_target_droplet",
  "target_mode": "droplet",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "public_mode_enabled": true,

  "instance_id": "demo-001",

  "droplet_name": "konnaxion-droplet",
  "droplet_host": "203.0.113.10",
  "host": "203.0.113.10",
  "droplet_user": "root",
  "ssh_user": "root",
  "user": "root",

  "ssh_key_path": "C:\\Users\\rejea\\.ssh\\id_ed25519",
  "ssh_port": "22",

  "remote_kx_root": "/opt/konnaxion",
  "remote_root": "/opt/konnaxion",
  "runtime_root": "/opt/konnaxion",

  "remote_capsule_dir": "/opt/konnaxion/capsules",
  "capsule_dir": "/opt/konnaxion/capsules",

  "domain": "203.0.113.10.sslip.io",
  "droplet_domain": "203.0.113.10.sslip.io",

  "remote_agent_url": "",
  "confirmed": true
}
```

`set_target_droplet` must reject missing `confirmed`.

Droplet target mode requires:

```text
target_mode = droplet
network_profile = public_vps
exposure_mode = public
droplet_host is present
droplet_user is present
ssh_key_path is present
ssh_port is present
remote_kx_root is present
remote_capsule_dir is present
domain is present
confirmed = true
```

`remote_capsule_dir` must be under `remote_kx_root`.

`remote_agent_url` should normally be blank. Blank means the Manager must reach the private Droplet Agent through SSH-local curl:

```text
ssh root@<droplet_host> "curl http://127.0.0.1:8765/v1/health"
```

---

### 3.5 Bootstrap Droplet Agent

```json
{
  "action": "bootstrap_droplet_agent",
  "target_mode": "droplet",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "public_mode_enabled": true,

  "instance_id": "demo-001",

  "droplet_name": "konnaxion-droplet",
  "droplet_host": "203.0.113.10",
  "host": "203.0.113.10",
  "droplet_user": "root",
  "ssh_user": "root",
  "user": "root",

  "ssh_key_path": "C:\\Users\\rejea\\.ssh\\id_ed25519",
  "ssh_port": "22",

  "remote_kx_root": "/opt/konnaxion",
  "remote_root": "/opt/konnaxion",
  "runtime_root": "/opt/konnaxion",

  "remote_capsule_dir": "/opt/konnaxion/capsules",
  "capsule_dir": "/opt/konnaxion/capsules",

  "domain": "203.0.113.10.sslip.io",
  "droplet_domain": "203.0.113.10.sslip.io",

  "remote_agent_url": "",
  "confirmed": true
}
```

`bootstrap_droplet_agent` is a first-time Droplet preparation action.

It must:

```text
connect to the Droplet over SSH
create the canonical /opt/konnaxion runtime layout
install or refresh the Konnaxion Manager/Agent code
install required runtime dependencies
install or refresh the Konnaxion Agent systemd service
start the Agent bound to 127.0.0.1:8765
verify http://127.0.0.1:8765/v1/health from inside the Droplet
```

It must not require:

```text
capsule_file
capsule_path
```

It must not expose Agent port `8765` publicly.

Bootstrap currently requires `droplet_user=root` because it may install packages, write `/etc/systemd/system/konnaxion-agent.service`, reload systemd, enable the service, and start it.

A successful bootstrap result must include enough data to verify:

```text
remote_kx_root
remote_manager_dir
remote_agent_health_url = http://127.0.0.1:8765/v1/health
systemd_service = konnaxion-agent.service
```

---

### 3.6 Check Droplet Agent

```json
{
  "action": "check_droplet_agent",
  "target_mode": "droplet",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "public_mode_enabled": true,

  "instance_id": "demo-001",

  "droplet_name": "konnaxion-droplet",
  "droplet_host": "203.0.113.10",
  "host": "203.0.113.10",
  "droplet_user": "root",

  "ssh_key_path": "C:\\Users\\rejea\\.ssh\\id_ed25519",
  "ssh_port": "22",

  "remote_kx_root": "/opt/konnaxion",
  "remote_capsule_dir": "/opt/konnaxion/capsules",

  "domain": "203.0.113.10.sslip.io",
  "droplet_domain": "203.0.113.10.sslip.io",

  "remote_agent_url": "",
  "confirmed": true
}
```

`check_droplet_agent` must not require:

```text
capsule_file
capsule_path
```

When `remote_agent_url` is blank, the check must use SSH-local curl against:

```text
http://127.0.0.1:8765/v1/health
```

from inside the Droplet.

---

### 3.7 Copy Capsule to Droplet

```json
{
  "action": "copy_capsule_to_droplet",
  "target_mode": "droplet",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "public_mode_enabled": true,

  "instance_id": "demo-001",

  "capsule_file": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",
  "capsule_path": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",

  "droplet_name": "konnaxion-droplet",
  "droplet_host": "203.0.113.10",
  "host": "203.0.113.10",
  "droplet_user": "root",

  "ssh_key_path": "C:\\Users\\rejea\\.ssh\\id_ed25519",
  "ssh_port": "22",

  "remote_kx_root": "/opt/konnaxion",
  "remote_capsule_dir": "/opt/konnaxion/capsules",

  "domain": "203.0.113.10.sslip.io",
  "droplet_domain": "203.0.113.10.sslip.io",

  "remote_agent_url": "",
  "confirmed": true
}
```

`copy_capsule_to_droplet` requires:

```text
capsule_file
```

It must copy the capsule to:

```text
/opt/konnaxion/capsules/<capsule filename>.kxcap
```

---

### 3.8 Deploy Droplet

```json
{
  "action": "deploy_droplet",
  "target_mode": "droplet",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "public_mode_enabled": true,

  "instance_id": "demo-001",

  "capsule_file": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",
  "capsule_path": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",

  "droplet_name": "konnaxion-droplet",
  "droplet_host": "203.0.113.10",
  "host": "203.0.113.10",
  "droplet_user": "root",

  "ssh_key_path": "C:\\Users\\rejea\\.ssh\\id_ed25519",
  "ssh_port": "22",

  "remote_kx_root": "/opt/konnaxion",
  "remote_capsule_dir": "/opt/konnaxion/capsules",

  "domain": "203.0.113.10.sslip.io",
  "droplet_domain": "203.0.113.10.sslip.io",

  "remote_agent_url": "",
  "confirmed": true
}
```

`deploy_droplet` requires:

```text
capsule_file
```

It must run the full workflow:

```text
verify local capsule
copy capsule to Droplet
ensure remote runtime directories
check private Droplet Agent
import capsule through SSH-local Agent transport
create or update instance
set public_vps network profile
run Security Gate
start instance
```

---

### 3.9 Start Droplet Instance

```json
{
  "action": "start_droplet_instance",
  "target_mode": "droplet",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "public_mode_enabled": true,

  "instance_id": "demo-001",

  "capsule_file": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",

  "droplet_name": "konnaxion-droplet",
  "droplet_host": "203.0.113.10",
  "host": "203.0.113.10",
  "droplet_user": "root",

  "ssh_key_path": "C:\\Users\\rejea\\.ssh\\id_ed25519",
  "ssh_port": "22",

  "remote_kx_root": "/opt/konnaxion",
  "remote_capsule_dir": "/opt/konnaxion/capsules",

  "domain": "203.0.113.10.sslip.io",
  "droplet_domain": "203.0.113.10.sslip.io",

  "remote_agent_url": "",
  "confirmed": true
}
```

`start_droplet_instance` requires:

```text
capsule_file
```

The file is required so the GUI keeps the same capsule context as deploy/copy operations.

---

## 4. Canonical Droplet Action Sets

Use the same sets in:

```text
kx_manager/ui/form_targets.py
tests
kx_manager/ui/page_parts/targets.py
kx_manager/ui/page_parts/deploy.py
```

```python
DROPLET_ACTIONS: frozenset[str] = frozenset(
    {
        "set_target_droplet",
        "bootstrap_droplet_agent",
        "deploy_droplet",
        "check_droplet_agent",
        "copy_capsule_to_droplet",
        "start_droplet_instance",
    }
)

DROPLET_OPERATION_ACTIONS: frozenset[str] = frozenset(
    {
        "bootstrap_droplet_agent",
        "deploy_droplet",
        "check_droplet_agent",
        "copy_capsule_to_droplet",
        "start_droplet_instance",
    }
)

DROPLET_CAPSULE_REQUIRED_ACTIONS: frozenset[str] = frozenset(
    {
        "deploy_droplet",
        "copy_capsule_to_droplet",
        "start_droplet_instance",
    }
)
```

For these operation actions, force/default:

```python
target_mode = "droplet"
network_profile = "public_vps"
exposure_mode = "public"
confirmed = True
```

`set_target_droplet` must still reject missing `confirmed`.

Operation actions may force confirmation because they are explicit Droplet operation forms.

`bootstrap_droplet_agent` and `check_droplet_agent` must not require `capsule_file`.

`deploy_droplet`, `copy_capsule_to_droplet`, and `start_droplet_instance` must require `capsule_file`.

---

## 5. Droplet Alias Normalization

Droplet forms may submit compatibility aliases.

Normalize these aliases before validation:

```text
ssh_user       -> droplet_user
user           -> droplet_user
remote_root    -> remote_kx_root
runtime_root   -> remote_kx_root
capsule_dir    -> remote_capsule_dir
droplet_domain -> domain
```

For Agent network/profile calls:

```text
domain -> host
droplet_domain -> host
```

Do not send `domain` to Agent endpoints unless that endpoint explicitly accepts it.

---

## 6. Remote Agent URL Rules

Blank `remote_agent_url` means:

```text
use SSH-local curl to http://127.0.0.1:8765/v1 inside the Droplet
```

The GUI must ignore stale local tunnel URLs for Droplet payloads:

```text
http://127.0.0.1:18765/v1
http://localhost:18765/v1
```

Those URLs point to the Manager machine, not the Droplet.

The GUI may use direct HTTP only when `remote_agent_url` is explicitly configured to a real, non-loopback Agent endpoint that matches the selected remote target.

The preferred secure mode is still:

```text
Agent private on 127.0.0.1:8765 inside Droplet
Manager calls Agent through SSH-local curl
```

The Agent port `8765` must not be opened publicly.

---

## 7. Deploy Page Rendering Rules

`kx_manager/ui/page_parts/deploy.py` should render deployment and operation actions:

```text
deploy_local
deploy_intranet
bootstrap_droplet_agent
check_droplet_agent
copy_capsule_to_droplet
deploy_droplet
start_droplet_instance
```

Droplet operation cards must appear in this operator workflow order:

```text
1. Bootstrap Droplet Agent
2. Check Droplet Agent
3. Copy Capsule to Droplet
4. Deploy Droplet
5. Start Droplet Instance
```

For these actions, use full Droplet operation forms, not hidden-only buttons:

```text
bootstrap_droplet_agent
check_droplet_agent
copy_capsule_to_droplet
deploy_droplet
start_droplet_instance
```

`deploy_droplet`, `copy_capsule_to_droplet`, and `start_droplet_instance` must include visible `capsule_file`.

`bootstrap_droplet_agent` and `check_droplet_agent` do not require `capsule_file` and must not submit `capsule_file`, even as hidden input.

`deploy_local` and `deploy_intranet` may remain compact button forms, but their payloads must come from:

```text
local_payload(context)
intranet_payload(context)
```

The deploy page contract puts Droplet operations on:

```text
/ui/deploy
```

not on:

```text
/ui/targets
```

Therefore `bootstrap_droplet_agent` belongs on `/ui/deploy`.

---

## 8. Target Page Rendering Rules

`/ui/targets` must render target-selection forms only:

```text
set_target_local
set_target_intranet
set_target_temporary_public
set_target_droplet
```

`/ui/targets` must not render deployment/operation forms:

```text
deploy_local
deploy_intranet
bootstrap_droplet_agent
check_droplet_agent
copy_capsule_to_droplet
deploy_droplet
start_droplet_instance
```

---

## 9. Test Payload Alignment

Tests that build base payloads for Droplet actions must include `bootstrap_droplet_agent` in the Droplet action set.

```python
if action in {
    "set_target_droplet",
    "bootstrap_droplet_agent",
    "deploy_droplet",
    "check_droplet_agent",
    "copy_capsule_to_droplet",
    "start_droplet_instance",
}:
    base.update(
        {
            "target_mode": "droplet",
            "network_profile": "public_vps",
            "exposure_mode": "public",
            "droplet_name": "ubuntu-s-1vcpu-2gb-tor1",
            "droplet_host": "203.0.113.10",
            "host": "203.0.113.10",
            "droplet_user": "root",
            "ssh_key_path": str(ssh_key_path),
            "ssh_port": "22",
            "remote_kx_root": "/opt/konnaxion",
            "runtime_root": "/opt/konnaxion",
            "remote_capsule_dir": "/opt/konnaxion/capsules",
            "capsule_dir": "/opt/konnaxion/capsules",
            "domain": "203.0.113.10.sslip.io",
            "droplet_domain": "203.0.113.10.sslip.io",
            "confirmed": "true",
        }
    )
```

For actions in:

```text
bootstrap_droplet_agent
check_droplet_agent
```

tests must assert:

```text
capsule_file is not required
capsule_path is not required
capsule_file is not submitted, even as hidden input
```

For actions in:

```text
deploy_droplet
copy_capsule_to_droplet
start_droplet_instance
```

tests must assert:

```text
capsule_file is required
capsule_file is visible in the form
```

---

## 10. Required UI Labels

Use these exact labels:

```text
Check Manager
Check Agent
Select Source Folder
Select Output Folder
Build Capsule
Rebuild Capsule
Verify Capsule
Import Capsule
List Capsules
View Capsule
Create Instance
Update Instance
Start Instance
Stop Instance
Restart Instance
Instance Status
View Logs
Instance Health
Open Instance
Rollback
Create Backup
List Backups
Verify Backup
Restore Backup
Restore Backup New
Test Restore Backup
Run Security Check
Set Network Profile
Disable Public Mode
Set Local Target
Set Intranet Target
Set Droplet Target
Set Temporary Public Target
Deploy Local
Deploy Intranet
Bootstrap Droplet Agent
Deploy Droplet
Check Droplet Agent
Copy Capsule to Droplet
Start Droplet Instance
Open Manager Docs
Open Agent Docs
```

Danger labels must include:

```text
Bootstrap Droplet Agent
Deploy Droplet
Copy Capsule to Droplet
Start Droplet Instance
Disable Public Mode
Rollback
Restore Backup
Restore Backup New
```

`Bootstrap Droplet Agent` is a danger/privileged operation because it can install packages, write systemd service files, enable a service, and start services on the target host.

---

## 11. Droplet Bootstrap Gating

`bootstrap_droplet_agent` is allowed only when:

```text
target_mode = droplet
network_profile = public_vps
exposure_mode = public
droplet_host is present
droplet_user is present
ssh_key_path is present
ssh_port is present
remote_kx_root is present
remote_capsule_dir is present
domain is present
confirmed = true
```

`bootstrap_droplet_agent` must reject private/intranet/default payloads.

`bootstrap_droplet_agent` must not require `capsule_file`.

`bootstrap_droplet_agent` must not expose Agent port `8765` publicly.

A successful bootstrap result must include enough data to verify:

```text
remote_kx_root
remote_manager_dir
remote_agent_health_url = http://127.0.0.1:8765/v1/health
systemd_service = konnaxion-agent.service
```

---

## 12. Public Exposure / Droplet Gating

Public exposure is allowed only when:

```text
target_mode = droplet
network_profile = public_vps
exposure_mode = public
confirmed = true
domain is present
```

Temporary public exposure is allowed only when:

```text
target_mode = temporary_public
network_profile = public_temporary
exposure_mode = temporary_tunnel
public_mode_expires_at is present
confirmed = true
```

Private/local/intranet payloads must not include public Droplet fields.

Droplet payloads must never inherit:

```text
target_mode = intranet
network_profile = intranet_private
exposure_mode = private
```

The following submitted payload must never reach dispatch uncorrected:

```json
{
  "action": "copy_capsule_to_droplet",
  "target_mode": "intranet",
  "network_profile": "intranet_private",
  "exposure_mode": "private"
}
```

Validated output for Droplet operation actions must normalize to:

```json
{
  "target_mode": "droplet",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "confirmed": true
}
```

with all required Droplet fields present.

---

## 13. Action-Specific Capsule Requirements

Must require `capsule_file`:

```text
deploy_droplet
copy_capsule_to_droplet
start_droplet_instance
```

Must not require `capsule_file`:

```text
bootstrap_droplet_agent
check_droplet_agent
```

Must not submit `capsule_file`, even hidden:

```text
bootstrap_droplet_agent
check_droplet_agent
```

---

## 14. Normalized Result Shape

All GUI action results must normalize to:

```json
{
  "ok": true,
  "action": "action_name",
  "instance_id": "demo-001",
  "message": "Human-readable message.",
  "data": {},
  "stdout": null,
  "stderr": null,
  "returncode": null
}
```

Droplet bootstrap success must include:

```json
{
  "remote_kx_root": "/opt/konnaxion",
  "remote_manager_dir": "/opt/konnaxion/manager",
  "remote_agent_health_url": "http://127.0.0.1:8765/v1/health",
  "systemd_service": "konnaxion-agent.service",
  "agent_transport": "ssh"
}
```

---

## 15. Required Tests

Create or update:

```text
tests/test_manager_ui_action_coverage.py
tests/test_manager_ui_routes.py
tests/test_manager_ui_forms.py
tests/test_fastapi_ui_page_split.py
tests/test_manager_ui_target_modes.py
tests/test_ui_form_targets.py
tests/test_ui_page_targets.py
tests/test_ui_page_deploy.py
```

The test set must verify:

```text
bootstrap_droplet_agent action exists
bootstrap_droplet_agent label exists
bootstrap_droplet_agent route exists
bootstrap_droplet_agent form model exists
bootstrap_droplet_agent appears on /ui/deploy
bootstrap_droplet_agent does not appear on /ui/targets
bootstrap_droplet_agent appears before check/deploy in Droplet workflow order
bootstrap_droplet_agent submits canonical droplet/public_vps/public values
bootstrap_droplet_agent requires confirmation
bootstrap_droplet_agent does not require capsule_file
bootstrap_droplet_agent does not submit capsule_file
check_droplet_agent does not require capsule_file
deploy/copy/start require capsule_file
Droplet operation actions never inherit intranet defaults
Droplet operation actions include required SSH and remote root fields
```

---

## 16. Required Commands

Run:

```powershell
uv run python -m compileall kx_manager/ui kx_manager/services tests
uv run pytest -q
```

Expected result:

```text
pytest passes
```

---

## 17. Done Definition

This contract is satisfied when:

```text
/ui/deploy renders Bootstrap Droplet Agent first in the Droplet workflow
bootstrap_droplet_agent has a POST route
bootstrap_droplet_agent validates Droplet/public_vps/public payloads
bootstrap_droplet_agent rejects private/intranet/default payloads
bootstrap_droplet_agent does not require capsule_file
bootstrap_droplet_agent starts the remote Agent privately on 127.0.0.1:8765
check/deploy/copy/start continue to use the same canonical Droplet payload normalization
remote_agent_url blank means SSH-local Agent transport
no Droplet operation opens port 8765 publicly
pytest passes
```


