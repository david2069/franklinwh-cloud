# Integration Plan: CLI, Diagnostics, Metrics & Testing

This document specifies the design, implementation phases, and test plans to integrate the newly-mapped 13 HAR endpoints and schema fixes into the command-line interface (CLI), diagnostic snapshot tools, metrics reporting, and local FastAPI emulator.

---

## Phase 1: CLI Commands Expansion

The newly added client mixin methods must be exposed via user-facing CLI subcommands in `franklinwh_cloud/cli_commands/` and registered in `cli.py`.

### 1. New Command: `system-setting` (or alias `settings`)
Expose system-level settings configured in the aGate hardware.
- **Location:** `franklinwh_cloud/cli_commands/settings.py` (New file)
- **CLI Options:**
  - `franklinwh-cli system-setting` (no args): Fetches system settings via `get_system_settings()` and displays them in a formatted Key-Value tabular view.
  - `franklinwh-cli system-setting --set-pcs [0|1]`: Updates the PCS discharge enable flag by calling `update_system_settings(is_pcs_dischg_en=val)`.
- **Placeholder Redaction (AP-3):** Ensure that any serial numbers or coordinates (such as the gateway serial) in this response are masked or redacted in console outputs by default, unless `--json` is specified without redaction.

### 2. VPP and Compliance Integration in `tou` / `status`
Expose Virtual Power Plant (VPP) eligibility and utility compliance settings.
- **Location:** `franklinwh_cloud/cli_commands/tou.py` and `franklinwh_cloud/cli_commands/status.py`
- **CLI Options:**
  - Add `--vpp` option to `franklinwh-cli tou`: Displays a clean section showing:
    - VPP eligibility status (`check_vpp_eligibility()`)
    - AI Dispatch Invitation status (`check_ai_dispatch_invitation()`)
    - AI Offline Disable Flag (`get_ai_offline_disable_flag()`)
    - JA12 Compliance Capacity details (`query_compliance_capacity()`)
    - NPS show tip and pop-up details (`get_nps_show_tip()`, `whether_popup()`)

### 3. Notification Event History
Add a command to view device alarms and system event logs.
- **Location:** `franklinwh_cloud/cli_commands/events.py` (New file)
- **CLI Options:**
  - `franklinwh-cli events` (or `franklinwh-cli status --events`):
    - Fetches recent messages using `get_messages_by_type(event_types="17,43,44")` (representing alarms, smart circuit toggles, and compliance events).
    - Displays results in chronological order with timestamps, event types, and descriptions.

---

## Phase 2: Diagnostics & Snapshot Enhancement

Diagnostics and support snapshots must collect the new data points to provide comprehensive system states for remote troubleshooting.

### 1. Diagnostic Checks (`diag.py`)
Update `franklinwh_cloud/cli_commands/diag.py`:
- Add a new **"System Controls & Settings"** block executing `get_system_settings()`. Reports electrical supply rating, PCS discharge status, RSD enable, and export power limits.
- Add a **"Programs & Compliance"** block executing `check_vpp_eligibility()` and `query_compliance_capacity()`. Displays whether the system is enrolled in California JA12 compliance cycles and current VPP eligibility status.

### 2. Support Snapshot (`support.py`)
Update `franklinwh_cloud/cli_commands/support.py`:
- Update `collect_snapshot()` to call:
  - `get_system_settings()` (appended under `"system_settings"`)
  - `check_vpp_eligibility()` and `query_compliance_capacity()` (appended under `"programmes"`)
  - `query_terminal_user_info()` (appended under `"identity"`)
  - `get_messages_by_type()` (appended under `"notifications_history"`)
- **Crucial Update to `redact_snapshot()` (AP-3):**
  - Mask email addresses in the newly added `terminal_user_info` response.
  - Mask `gatewayId` in `system_settings`.
  - Scrub specific message content in `notifications_history` that may contain installer name/phone information.

---

## Phase 3: Metrics Instrumentation

Track API coverage and performance for the new endpoints.
- Update `franklinwh_cloud/metrics.py` to ensure that method metrics capture calls to the new endpoints (e.g. `getSystemSetting`, `updateSystemSetting`, `checkUserVppEligibility`, `queryComplianceCapacity`, etc.).
- Update `cli_commands/metrics.py` to print summary counters for these new APIs in the **"Endpoints"** display list.
- Optional/non-critical helper endpoints (like NPS tips, NPS popups, and user resource trees) must not cause CLI failures on exceptions. They must be wrapped in try/catch logs that record a metric error counter but continue execution gracefully.

---

## Phase 4: Local FastAPI Emulator Integration

Ensure testing is independent of live internet connections by updating the emulator.
- **Location:** `emulator/main.py`
- Add FastAPI routes returning synthetic responses:
  - `GET /hes-gateway/terminal/system/getSystemSetting`
  - `POST /hes-gateway/terminal/system/updateSystemSetting`
  - `GET /hes-gateway/terminal/aiDispatch/checkAiDispatchInvitation`
  - `GET /hes-gateway/terminal/aiDispatch/getAiOfflineDisableFlag`
  - `GET /hes-gateway/terminal/checkUserVppEligibility`
  - `GET /hes-gateway/terminal/ja12/queryComplianceCapacity`
  - `POST /hes-gateway/terminal/tou/notify/ai/cache`
  - `POST /hes-gateway/terminal/nps/getNpsShowTip`
  - `GET /hes-gateway/terminal/feedback/whetherPopUp`
  - `GET /hes-gateway/terminal/listDeviceMessagesByType`
  - `GET /hes-gateway/common/country/selectRunLogList`
  - `GET /hes-gateway/common/getPageByTypeList`
  - `GET /hes-gateway/terminal/v2/queryTerminalUserInfo`
  - `POST /hes-gateway/terminal/v2/loginOut`
  - `POST /hes-gateway/terminal/updateTerUserFcmToken`

### Mock Data Fixtures (AP-3 Compliant)
```json
// system settings mock
{
  "code": 200,
  "message": "Query success!",
  "result": {
    "gatewayId": "10060006AXXXXXXXXX",
    "electricSupply": 63,
    "ratedGridVolt": 1,
    "ratedGridHz": 1,
    "offGridFlag": 0,
    "gridExportEnable": 1,
    "gridSoftLimit": -1,
    "gridHardLimit": -1,
    "apowerNumber": 1,
    "countryId": 3,
    "isThreePhaseInstall": 0,
    "threePhPvEnb": 0,
    "pcsSetFlag": true,
    "rsdEnable": 0,
    "isPcsDischgEn": 1
  },
  "success": true
}
```

---

## Test & Verification Plan

### 1. Automated Tests (Unit & Mock)
Write offline pytest test cases in `tests/test_cli_new_endpoints.py`:
- **Mock CLI Parser Verification:** Verify that `franklinwh-cli system-setting` parses correctly and raises error on invalid parameters (e.g. `--set-pcs 3`).
- **Snapshot Integration Tests:** Mock client responses for all new methods and assert that `collect_snapshot()` generates correct nested structures.
- **Redaction Verification:** Run `redact_snapshot()` on a mock snapshot containing the new fields and assert that emails, MACs, SSIDs, and serial numbers are properly masked.
- **API Metrics Assertion:** Run calls through a mock client and assert that `calls_by_endpoint` increments correctly for the new URLs.

### 2. Emulator Integration Tests
Write an integration script `tests/test_emulator_flow.py` running against a running emulator instance:
1. Start the FastAPI emulator locally.
2. Direct the client library to the emulator endpoint (e.g. `http://localhost:8080`).
3. Run the CLI commands (`status`, `system-setting`, `diag`, `support`) and assert that they execute with status code 0 and display expected data structures without crash.
