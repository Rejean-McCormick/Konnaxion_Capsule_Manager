doc_id: DOC-17B
title: Konnaxion GUI Action UI and Test Contract
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: technical-contract
owner: Konnaxion
last_updated: 2026-05-01
depends_on:
  - DOC-16_Konnaxion_Manager_GUI_Technical_Contract.md
  - DOC-17_Konnaxion_GUI_Action_Coverage_Contract.md
  - DOC-17A_Konnaxion_GUI_Action_Payload_Contract.md
  - DOC-18_Konnaxion_GUI_Target_Modes.md
---

# DOC-17B — Konnaxion GUI Action UI and Test Contract

## 1. Purpose

This document defines the GUI button coverage, safety gating, canonical labels, required tests, and acceptance criteria for the Konnaxion Capsule Manager GUI.

Action identity, backend ownership, route coverage, Agent endpoints, and client method requirements are defined in:

```text
DOC-17_Konnaxion_GUI_Action_Coverage_Contract.md
````

Payload shape, alias normalization, Droplet action normalization, and normalized action result shape are defined in:

```text
DOC-17A_Konnaxion_GUI_Action_Payload_Contract.md
```

This document exists to ensure the GUI is usable as an operator surface and not only as a visual scaffold.

---

## 2. UI Button Coverage Rule

The GUI must provide all required actions across the page set.

A button may appear on one primary page and optionally as a shortcut elsewhere.

Every rendered button or form must submit one canonical `UiAction` or open one browser-only link.

No GUI button may exist unless it maps to:

```text
UiAction
action route
browser link
validated form model
action dispatcher handler
normalized action result
```

---

## 3. Dashboard Page Coverage

The Dashboard should include shortcuts for:

```text
Check Manager
Check Agent
Build Capsule
Verify Capsule
Import Capsule
Create Instance
Run Security Check
Start Instance
Open Manager Docs
Open Agent Docs
```

Required canonical actions:

```text
check_manager
check_agent
build_capsule
verify_capsule
import_capsule
create_instance
run_security_check
start_instance
open_manager_docs
open_agent_docs
```

Browser-only actions on this page:

```text
open_manager_docs
open_agent_docs
```

---

## 4. Settings Page Coverage

The Settings page must include:

```text
Select Source Folder
Select Output Folder
```

Required canonical actions:

```text
select_source_folder
select_capsule_output_folder
```

---

## 5. Capsules Page Coverage

The Capsules page must include:

```text
Build Capsule
Verify Capsule
Import Capsule
List Capsules
View Capsule
```

The Capsules page should include:

```text
Rebuild Capsule
```

Required canonical actions:

```text
build_capsule
verify_capsule
import_capsule
list_capsules
view_capsule
rebuild_capsule
```

---

## 6. Instances Page Coverage

The Instances page must include:

```text
Create Instance
Update Instance
Start Instance
Stop Instance
Restart Instance
Instance Status
View Logs
Instance Health
Rollback
Open Instance
```

Required canonical actions:

```text
create_instance
update_instance
start_instance
stop_instance
restart_instance
instance_status
view_logs
view_health
rollback_instance
open_instance
```

Browser-only actions on this page:

```text
open_instance
```

---

## 7. Backups Page Coverage

The Backups page must include:

```text
Create Backup
List Backups
Verify Backup
```

Required canonical actions:

```text
create_backup
list_backups
verify_backup
```

---

## 8. Restore Page Coverage

The Restore page must include:

```text
Restore Backup
Restore Backup New
Test Restore Backup
Rollback
```

Required canonical actions:

```text
restore_backup
restore_backup_new
test_restore_backup
rollback_instance
```

---

## 9. Network Page Coverage

The Network page must include:

```text
Set Network Profile
Disable Public Mode
```

Required canonical actions:

```text
set_network_profile
disable_public_mode
```

---

## 10. Security Page Coverage

The Security page must include:

```text
Run Security Check
```

Required canonical actions:

```text
run_security_check
```

---

## 11. Targets Page Coverage

The Targets page must include target configuration actions only:

```text
Set Local Target
Set Intranet Target
Set Droplet Target
Set Temporary Public Target
```

Required canonical actions:

```text
set_target_local
set_target_intranet
set_target_droplet
set_target_temporary_public
```

Deployment operation actions should be moved to a dedicated Deployment page when the Targets page layout becomes too large.

---

## 12. Deployment Page Coverage

The Deployment page should include:

```text
Deploy Local
Deploy Intranet
Deploy Droplet
Check Droplet Agent
Copy Capsule to Droplet
Start Droplet Instance
```

Required canonical actions:

```text
deploy_local
deploy_intranet
deploy_droplet
check_droplet_agent
copy_capsule_to_droplet
start_droplet_instance
```

If `/ui/deployment` is introduced, update the route contract and tests accordingly.

The Deployment page must keep Droplet operation controls explicit and visible for required public fields:

```text
instance_id
droplet_name
droplet_host
droplet_user
ssh_key_path
ssh_port
remote_kx_root
remote_capsule_dir
domain
confirmed
```

The `check_droplet_agent` form must not render `capsule_file`, including as a hidden input.

The following actions require `capsule_file` or `capsule_path`:

```text
deploy_droplet
copy_capsule_to_droplet
start_droplet_instance
```

---

## 13. Safety Gating

### 13.1 Start button

Start must be disabled when:

```text
state in importing, verifying, starting, stopping, updating, rolling_back, security_blocked
security_status = FAIL_BLOCKING
```

Start may be enabled when:

```text
state in created, ready, stopped, degraded
security_status in PASS, WARN, UNKNOWN
```

If `security_status = UNKNOWN`, clicking Start must run Security Gate first or require explicit confirmation.

---

### 13.2 Public exposure

If:

```text
network_profile = public_temporary
```

then:

```text
target_mode = temporary_public
exposure_mode = temporary_tunnel
public_mode_expires_at is required
confirmed = true
```

If:

```text
network_profile = public_vps
```

then:

```text
target_mode = droplet
exposure_mode = public
domain is required
droplet_host is required
confirmed = true
```

Public exposure must never be the default.

---

### 13.3 Destructive actions

These actions require confirmation:

```text
stop_instance
restore_backup
restore_backup_new
rollback_instance
disable_public_mode
set_target_temporary_public
set_target_droplet
deploy_droplet
start_droplet_instance
```

---

### 13.4 Rollback

If:

```text
restore_data = true
```

then:

```text
backup_id is required
```

---

### 13.5 Droplet deployment

Droplet deployment must be blocked unless:

```text
target_mode = droplet
network_profile = public_vps
exposure_mode = public
droplet_host is set
droplet_user is set
ssh_key_path exists
remote_kx_root is set
remote_capsule_dir is set
remote_capsule_dir is under remote_kx_root
domain is set
confirmed = true
```

Droplet deployment must not inherit intranet defaults from the standard private payload builder.

This submitted payload must never reach dispatch uncorrected:

```json
{
  "action": "copy_capsule_to_droplet",
  "target_mode": "intranet",
  "network_profile": "intranet_private",
  "exposure_mode": "private"
}
```

Validated output for that action must become:

```json
{
  "action": "copy_capsule_to_droplet",
  "target_mode": "droplet",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "confirmed": true
}
```

with required Droplet fields present.

---

## 14. Canonical Labels

Use these exact user-facing labels:

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
Deploy Droplet
Check Droplet Agent
Copy Capsule to Droplet
Start Droplet Instance
Open Manager Docs
Open Agent Docs
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
```

If a dedicated Deployment page is introduced, also create or update:

```text
tests/test_ui_page_deployment.py
```

---

## 16. Required Action Coverage Tests

Required action coverage tests:

```text
test_all_uiactions_have_labels
test_all_uiactions_have_route_or_link
test_all_post_action_routes_start_with_ui_actions
test_all_required_actions_exist
test_no_extra_unmapped_actions_exist
test_build_capsule_action_exists
test_rebuild_capsule_action_exists
test_restart_instance_action_exists
test_instance_status_action_exists
test_list_backups_action_exists
test_test_restore_backup_action_exists
test_check_manager_action_exists
test_check_agent_action_exists
test_open_docs_actions_exist
test_target_actions_exist
test_droplet_actions_exist
test_deploy_actions_exist
test_action_payloads_use_canonical_network_profiles
test_action_payloads_use_canonical_exposure_modes
test_action_payloads_use_canonical_docker_services
test_public_temporary_requires_expiration
test_public_vps_requires_confirmation
test_rollback_restore_data_requires_backup_id
test_droplet_deploy_requires_host_user_key_remote_root
test_command_fallback_uses_shell_false
test_fastapi_ui_register_exists
test_streamlit_is_not_required_for_fastapi_ui_import
```

---

## 17. Required Droplet Regression Tests

Required Droplet regression tests:

```text
test_targets_page_copy_capsule_to_droplet_form_uses_droplet_payload
test_targets_page_droplet_operation_forms_do_not_submit_intranet_payload
test_targets_page_droplet_operation_forms_keep_required_public_fields_visible
test_droplet_payload_forces_public_vps_without_intranet_defaults
test_droplet_action_payload_validation_forces_canonical_values
test_droplet_payload_does_not_invent_domain_from_host
test_droplet_validation_rejects_missing_domain
test_droplet_capsule_required_actions_require_capsule_file
test_check_droplet_agent_does_not_require_capsule_file
test_droplet_operation_actions_force_canonical_public_vps_values
```

---

## 18. Required Page Layout Regression Tests

Required page layout tests:

```text
test_targets_page_renders_target_configuration_only
test_deployment_page_renders_deploy_actions
test_deployment_page_renders_droplet_operations
test_check_droplet_agent_form_has_no_capsule_file_input
test_droplet_operation_forms_keep_public_fields_visible
test_droplet_operation_forms_do_not_submit_intranet_payload
```

If Deployment actions remain on the Targets page temporarily, tests must still prove:

```text
Droplet operation required fields are visible.
check_droplet_agent does not submit capsule_file.
Droplet operation forms do not submit intranet payloads.
The page remains usable without hidden stale private target defaults.
```

---

## 19. Required Commands

Run:

```powershell
uv run python -m compileall kx_manager/ui kx_manager/services tests
uv run pytest -q
```

Expected result:

```text
pytest passes
```

Current known-good baseline:

```text
613 passed
```

---

## 20. Acceptance Criteria

The GUI action coverage is complete when:

```text
All required UiAction values exist.
Required GUI action count is 41.
Every UiAction has a label.
Every non-browser UiAction maps to a POST route.
Every browser-only UiAction maps to a link.
Every action route is registered by kx_manager/ui/app.py.
Every action validates canonical values.
No GUI button exists without a mapped action.
No mapped action lacks a GUI button.
Local target mode is represented.
Intranet target mode is represented.
Temporary public target mode is represented.
Droplet target mode is represented.
Deployment operations are represented.
Droplet operations never submit intranet payloads.
Droplet domain is required and is not silently invented from IP/host.
check_droplet_agent does not require or submit capsule_file.
pytest passes.
```

The GUI is considered usable instead of commands when an operator can do this in browser:

```text
Check Manager
Check Agent
Select Konnaxion source folder
Select capsule output folder
Build Capsule
Verify Capsule
Import Capsule
Create Instance
Update Instance
Start Instance
View Status
View Health
Run Security Check
View Logs
Create Backup
Stop Instance
Rollback or Restore when needed
Deploy Local
Deploy Intranet
Deploy Droplet
Check Droplet Agent
Copy Capsule to Droplet
Start Droplet Instance
```

without typing CLI commands.

---

## 21. Final Rule

Every GUI action must be traceable through this chain:

```text
button/label
  -> UiAction
  -> form model
  -> action route or browser link
  -> action dispatcher
  -> Manager service / client / route
  -> Agent endpoint / Builder service / Deploy service / CLI fallback
  -> normalized GuiActionResult
  -> rendered result panel
```

If any link in that chain is missing, the action is incomplete.

Droplet actions have one extra invariant:

```text
button/form
  -> Droplet payload builder
  -> target_mode=droplet
  -> network_profile=public_vps
  -> exposure_mode=public
  -> confirmed=true
  -> required Droplet fields
  -> validated action payload
  -> dispatch
```

Droplet actions must never inherit the private/intranet default payload.

---

## 22. Page Split Recommendation

The preferred layout is:

```text
/ui/targets
  target configuration only

/ui/deployment
  deploy and Droplet operation actions
```

The route contract must be updated if `/ui/deployment` is added.

The page split is accepted when:

```text
Targets page is readable.
Deployment actions are grouped separately.
All required action buttons still exist.
All action route tests pass.
All form validation tests pass.
No action coverage is lost.
```


