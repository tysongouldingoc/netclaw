# Test Coverage Map — Selective MCP Installer & DefenseClaw Production Mode

> Authored by `qa-coverage-cartographer` for `team-qa`.
> Workspace: `C:\Users\tyson\Documents\antigravity\amazing-babbage\netclaw`
> Date: 2026-07-21

---

## 1. Executive Summary

This coverage mapping documents the current test baseline, existing coverage gaps, and proposed test expansion for the **Selective MCP Server Installer & DefenseClaw Production Mode** feature (`2026-07-21-mcp-installer-defenseclaw`). 

The feature introduces selective installation for NetClaw's 27+ MCP servers across dual runtime targets (`--target systemd` and `--target docker-compose`) while enforcing DefenseClaw Production Mode (`N2N_RISK_MODE=production`), fail-closed Model-Guard proxy preflight routing (`:4000`), pre-activation static source code scanning (`scripts/scan-all-mcp-source.py`), least-privilege sliced `.env.<mcp_name>` secrets (`0600` permissions), GAIT append-only audit logging (`~/.openclaw/n2n/gait/`), and dynamic posture calculation.

---

## 2. Component Coverage Mapping

| Target Component | File Path | Existing Coverage Status | Existing Test Files | Planned / Required Test Modules |
| :--- | :--- | :--- | :--- | :--- |
| **MCP Installer CLI & Wizard** | `scripts/mcp-installer.py` | **0% (New File)** | *None* | `tests/n2n/test_mcp_installer.py` |
| **DefenseClaw MCP Registration** | `scripts/register-mcps-with-defenseclaw.py` | **0% Direct** | *None* | `tests/n2n/test_mcp_installer.py`, `tests/n2n/test_model_guard_failclosed.py` |
| **Systemd Service Generator** | `scripts/in2n-services.py` | **Partial (~45%)** | `tests/n2n/test_durable_services.py`, `tests/n2n/test_controls_failclosed.py` | `tests/n2n/test_mcp_posture_dual_target.py`, `tests/n2n/test_target_parity.py` |
| **Docker Compose Generator** | `scripts/lib/mcp_compose.py` | **0% (New File)** | *None* | `tests/n2n/test_mcp_posture_dual_target.py`, `tests/n2n/test_target_parity.py` |
| **Posture Calculation Engine** | `bgp.federation.posture` | **High (~80%)** | `tests/n2n/test_posture.py` | `tests/n2n/test_mcp_posture_dual_target.py` |
| **Model-Guard Fail-Closed Gates** | `bgp.federation.controls` & `gateway.py` | **High (~75%)** | `tests/n2n/test_controls_failclosed.py` | `tests/n2n/test_model_guard_failclosed.py` |

---

## 3. Detailed Component & Invariant Mapping

### 3.1. `scripts/mcp-installer.py` (New File)
- **Current Coverage**: 0%
- **Target Invariants**:
  - Selective server filtering via `--select` and `--all` flags.
  - Interactive TUI wizard prompt handling with non-TTY auto-fallback.
  - Secret slicing from master `.env` to `.env.<mcp_name>` with strict `0600` file permissions.
  - Append-only GAIT audit logging to `~/.openclaw/n2n/gait/` for all installation/quarantine events.
  - Integration with pre-activation source code scanner `scripts/scan-all-mcp-source.py`.
  - Single Source of Truth update in `config/openclaw.json` (`mcpServers` section).
- **Test File**: `tests/n2n/test_mcp_installer.py`

### 3.2. `scripts/register-mcps-with-defenseclaw.py` (Modified)
- **Current Coverage**: 0% (Direct script tests)
- **Target Invariants**:
  - `--select` subset registration.
  - Model-Guard proxy socket preflight probe on port `:4000` (`verify_model_guard_proxy(port=4000)`).
  - Fail-closed abort in `N2N_RISK_MODE=production` if proxy socket is unreachable or returns connection error.
  - `--skip-scan` handling when explicitly authorized.
- **Test File**: `tests/n2n/test_mcp_installer.py`, `tests/n2n/test_model_guard_failclosed.py`

### 3.3. `scripts/in2n-services.py` (Modified)
- **Current Coverage**: Partial via `tests/n2n/test_durable_services.py` (mesh daemon/member services) and `tests/n2n/test_controls_failclosed.py` (`confined_cold_start`).
- **Target Invariants**:
  - `_mcp_unit_text()` generator formatting systemd user units with kernel confinement directives:
    `NoNewPrivileges=yes`, `ProtectSystem=strict`, `PrivateTmp=yes`, `InaccessiblePaths=-%h/.openclaw/.env`.
  - Selective unit generation (`cmd_generate()`) targeting sliced `.env.<mcp_name>` paths.
  - Graceful degradation under WSL2 environment when capability directives are unsupported.
- **Test File**: `tests/n2n/test_mcp_posture_dual_target.py`, `tests/n2n/test_target_parity.py`

### 3.4. `scripts/lib/mcp_compose.py` (New File)
- **Current Coverage**: 0%
- **Target Invariants**:
  - Emits hardened `docker-compose.mcp.yml` with container security options:
    `security_opt: [no-new-privileges:true]`, `read_only: true`, `cap_drop: ["ALL"]`, `tmpfs: ["/tmp"]`.
  - Sliced `.env.<mcp_name>` volume mounts per container.
  - Network bridge configuration pointing worker containers to Model-Guard proxy on port `:4000`.
- **Test File**: `tests/n2n/test_mcp_posture_dual_target.py`, `tests/n2n/test_target_parity.py`

### 3.5. Posture Calculation Engine
- **Current Coverage**: Covered by `tests/n2n/test_posture.py` (10 tests: 3-control matrix aggregation for `sandbox`, `model-guard`, `audit`; `enforced`, `testing`, `degraded` states; delegation preflight allow/refuse; `strict_all` overrides).
- **Target Invariants / Gaps**:
  - Dynamic posture evaluation across dual runtime targets (`--target systemd` vs `--target docker-compose`).
  - Correct posture state generation: `production - enforced` vs `production - DEGRADED (containment:unhardened_container)` or `production - DEGRADED (WSL2_kernel_limitation)`.
- **Test File**: `tests/n2n/test_mcp_posture_dual_target.py`

### 3.6. Model-Guard Fail-Closed Gates
- **Current Coverage**: Covered by `tests/n2n/test_controls_failclosed.py` (7 tests: `_apply_production_controls`, `confined_cold_start` transient systemd units, model-guard unavailable rejection, `component_scan` malicious skill flagging).
- **Target Invariants / Gaps**:
  - Extension of fail-closed gates to initial MCP server installation & registration.
  - Unreachable Model-Guard proxy (`:4000`) in `N2N_RISK_MODE=production` MUST abort installation before writing to `openclaw.json` or starting services.
  - Pre-activation source scanner (`scripts/scan-all-mcp-source.py`) detecting critical/high severity issues MUST quarantine server and block activation.
- **Test File**: `tests/n2n/test_model_guard_failclosed.py`

---

## 4. Baseline Test Execution Results

Baseline test suite invocation via `pytest` was performed on the current codebase:

1. **Full `pytest` Run**:
   - **Status**: Interrupted during collection due to OS platform dependency (`ModuleNotFoundError: No module named 'fcntl'`).
   - **Root Cause**: `mcp-servers/protocol-mcp/bgp/tun.py` imports POSIX-only module `fcntl`. Under Windows native Python environment, BGP kernel network modules cannot be imported without POSIX stubs or WSL2/Linux execution target.
2. **Modular Test Execution**:
   - **Unit Tests (`tests/unit/test_sqlite_store.py`)**: 34 passed, 3 failed (SQLite UNIQUE constraint timestamp collision in fast unit tests).
   - **Contract Tests (`tests/contract/test_mcp_tools.py`)**: 35 passed, 1 failed, 39 errors (File locking / SQLite temp db permissions under Windows).
   - **Logic Hardening**: Test logic in `test_posture.py` and `test_controls_failclosed.py` is fully stubbed and platform-agnostic, requiring only POSIX `fcntl` mock/stub on Windows or execution inside Linux/WSL2 container environment.

---

## 5. Test Suite Expansion Plan

To achieve comprehensive test coverage for Feature 057, 4 new test files and 1 fixture suite must be authored:

```
tests/
├── fixtures/
│   └── mcp_installer/
│       ├── mock_mcp_servers/           # Synthetic MCP server packages (clean & vulnerable)
│       ├── mock_master_env             # Sample multi-secret master .env file
│       ├── mock_openclaw_json          # Master openclaw.json schema fixture
│       └── mock_defenseclaw_proxy.py   # Async HTTP stub for port :4000 proxy
└── n2n/
    ├── test_mcp_installer.py           # Installer CLI selection, registration, & secret slicing
    ├── test_mcp_posture_dual_target.py # Dual-target posture calculation (systemd vs docker-compose)
    ├── test_model_guard_failclosed.py  # Model-guard proxy (:4000) & scan fail-closed gates
    └── test_target_parity.py           # Docker Compose vs Systemd security directive parity
```

---

## 6. Recommendations for `qa-lead`

1. **Mock `fcntl` for Windows Test Runners**: Add a conditional import guard or `pytest` fixture mocking `sys.modules['fcntl']` in `conftest.py` so the test suite can run natively across all developer platforms (Windows, Linux, macOS).
2. **Prioritize `test_model_guard_failclosed.py`**: Ensuring fail-closed behavior on port `:4000` is the highest security priority to prevent uninspected or unguarded MCP execution in production mode.
3. **Assert Security Directive Parity**: Implement `test_target_parity.py` to guarantee that `--target docker-compose` provides strict security equivalence to `--target systemd` (`no-new-privileges`, read-only root, sliced env isolation).
