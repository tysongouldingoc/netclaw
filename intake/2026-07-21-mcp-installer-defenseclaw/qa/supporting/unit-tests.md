# Unit & Parity Test Design — Selective MCP Installer & DefenseClaw Production Mode

> Authored by `qa-unit-architect` for `team-qa`.
> **Scope Target:** `scripts/mcp-installer.py`, `scripts/register-mcps-with-defenseclaw.py`, `scripts/in2n-services.py`, `scripts/lib/mcp_compose.py`
> **Primary Artifact:** [change-brief.md](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/intake/2026-07-21-mcp-installer-defenseclaw/qa/change-brief.md)

---

## 1. Overview & Strategy

This specification details the unit and parity test architecture for verifying the Selective MCP Installer and DefenseClaw Production Mode controls. The test suite isolates logic using Pytest fixtures, mock sockets, and temp file system boundaries (`tmp_path`) to ensure fast, deterministic, zero-side-effect execution across test runs.

### Target Coverage Summary

| Test Module File | Focus Surface / Responsibility | Primary Risk Mitigated |
| :--- | :--- | :--- |
| `tests/n2n/test_mcp_installer.py` | Server selection CLI/TUI logic, `openclaw.json` registration updates, `.env.<mcp>` secret slicing & file mode `0600`. | Secret leakage & registration desynchronization. |
| `tests/n2n/test_mcp_posture_dual_target.py` | Posture engine calculation (`production - enforced` vs `degraded`), WSL2 kernel limitation fallback, systemd vs compose target posture. | Silent security degradation in production. |
| `tests/n2n/test_model_guard_failclosed.py` | Fail-closed pre-activation gates: Model-Guard proxy socket connectivity check (:4000), static scan aborts on critical vulnerabilities. | Execution of unvetted or unguarded MCP binaries. |
| `tests/n2n/test_target_parity.py` | Structural & directive parity verification between `systemd` user units and `docker-compose.mcp.yml` security profiles. | Security posture variance across execution environments. |

---

## 2. Detailed Test Specifications

### Module 1: `tests/n2n/test_mcp_installer.py`
**Target Components:** `scripts/mcp-installer.py`, `scripts/register-mcps-with-defenseclaw.py`

#### Test Cases

1. **`test_installer_server_discovery_and_selection()`**
   - **Description:** Verifies that `mcp-installer.py` correctly scans `mcp-servers/*/`, parses server manifests, and handles `--select` argument filtering vs interactive prompt selection.
   - **Inputs:** Mock directory structure in `tmp_path` containing `mcp-servers/github-mcp`, `mcp-servers/memory-mcp`, `mcp-servers/slack-mcp`. CLI arguments `--select github-mcp,memory-mcp`.
   - **Assertions:**
     - Only `github-mcp` and `memory-mcp` are included in the execution plan.
     - `slack-mcp` is marked as skipped.
     - Return code is `0`.

2. **`test_openclaw_json_registration_update()`**
   - **Description:** Validates atomic update of `~/.openclaw/config/openclaw.json` when adding or removing selected MCP servers.
   - **Inputs:** Initial `openclaw.json` with 1 server. Installer run with `--select github-mcp,warcraftlogs`.
   - **Assertions:**
     - `openclaw.json` `mcpServers` dictionary contains exact keys `github-mcp` and `warcraftlogs`.
     - Valid JSON structure preserved; existing unrelated keys in `openclaw.json` remain untouched.
     - Backup copy `openclaw.json.bak` generated prior to mutation.

3. **`test_secret_slicing_and_permission_0600()`**
   - **Description:** Ensures master `~/.openclaw/.env` is sliced into per-server `.env.<mcp_name>` files containing strictly required key subsets, with file permissions strictly set to `0600` (`-rw-------`).
   - **Inputs:** Master `.env` containing `GITHUB_TOKEN=secret123`, `TWILIO_SID=secret456`, `AWS_KEY=secret789`. Slicing rule for `github-mcp` requesting `GITHUB_TOKEN`.
   - **Assertions:**
     - Created file `.env.github-mcp` contains `GITHUB_TOKEN=secret123`.
     - `.env.github-mcp` does NOT contain `TWILIO_SID` or `AWS_KEY`.
     - `os.stat(env_file_path).st_mode & 0o777 == 0o600`.

4. **`test_non_interactive_tty_fallback()`**
   - **Description:** Validates CLI behavior when executed without a TTY (stdin detached) and missing required `--select` or `--all` flags.
   - **Inputs:** Detached `sys.stdin` (mocked `isatty() == False`), invocation with no flags.
   - **Assertions:**
     - Execution aborts immediately.
     - Exit code is `1`.
     - Stdout/stderr contains error message requiring explicit `--select` or `--all` in non-interactive mode.

---

### Module 2: `tests/n2n/test_mcp_posture_dual_target.py`
**Target Components:** `scripts/mcp-installer.py`, `bgp/federation/posture.py`

#### Test Cases

1. **`test_posture_all_controls_enforced()`**
   - **Description:** Verifies that when dual targets (`systemd` or `docker-compose`), proxy socket, static scan, and GAIT logging are active under `N2N_RISK_MODE=production`, posture resolves to `enforced`.
   - **Inputs:** Mock all probes returning `True` under `N2N_RISK_MODE=production`.
   - **Assertions:**
     - `posture["state"] == "enforced"`
     - `posture["missing"] == []`
     - `posture["summary"] == "production — enforced"`

2. **`test_posture_degraded_on_missing_control()`**
   - **Description:** Parametrized test checking individual control failures in production mode.
   - **Parametrization:**
     - `missing_control="model-guard"` -> proxy offline (:4000 unreachable)
     - `missing_control="gait"` -> audit log path non-writable
     - `missing_control="scan"` -> unverified source detected
   - **Assertions:**
     - `posture["state"] == "degraded"`
     - `posture["missing"] == [<missing_control>]`
     - `posture["summary"]` contains `"degraded"` and names the missing control.

3. **`test_wsl2_kernel_limitation_posture_degradation()`**
   - **Description:** Verifies WSL2 environment detection (where systemd kernel security directives are unsupported) gracefully degrades posture without hard failure.
   - **Inputs:** `os.uname()` or `/proc/version` containing `microsoft-standard-WSL2`, `--target systemd`.
   - **Assertions:**
     - `posture["state"] == "degraded"`
     - `posture["missing"] == ["systemd_kernel_confinement"]`
     - `posture["summary"] == "production — DEGRADED (WSL2_kernel_limitation)"`

4. **`test_target_specific_posture_evaluation()`**
   - **Description:** Verifies posture engine evaluates target-specific prerequisites (Docker daemon running for `docker-compose` target vs Systemd user bus accessible for `systemd` target).
   - **Assertions:**
     - Target `docker-compose` with Docker socket down reports `degraded` (`missing=["docker_daemon"]`).
     - Target `systemd` with `DBUS_SESSION_BUS_ADDRESS` unset reports `degraded` (`missing=["systemd_user_bus"]`).

---

### Module 3: `tests/n2n/test_model_guard_failclosed.py`
**Target Components:** `scripts/register-mcps-with-defenseclaw.py`, `scripts/scan-all-mcp-source.py`

#### Test Cases

1. **`test_proxy_unreachable_failclosed_in_production()`**
   - **Description:** Validates that when `N2N_RISK_MODE=production` and Model-Guard proxy socket on port `:4000` is unreachable, server registration and activation fail closed.
   - **Inputs:** `N2N_RISK_MODE=production`, port `:4000` closed (connection refused / socket timeout).
   - **Assertions:**
     - `verify_model_guard_proxy(port=4000)` returns `False`.
     - `register-mcps-with-defenseclaw.py` exits with non-zero exit code (`1`).
     - `openclaw.json` remains unmodified.
     - GAIT log records `REGISTRATION_ABORTED_PROXY_UNREACHABLE`.

2. **`test_static_scan_high_risk_finding_abort()`**
   - **Description:** Verifies that pre-activation static scan detecting High or Critical security findings aborts the installation flow.
   - **Inputs:** Mock `scan-all-mcp-source.py` returning exit code `2` with simulated finding (e.g. unescaped subprocess call in MCP server source code).
   - **Assertions:**
     - Preflight gate catches scan failure.
     - Installer halts before service unit creation or compose generation.
     - Console outputs scan error summary.

3. **`test_proxy_and_scan_bypass_in_testing_mode()`**
   - **Description:** Confirms that when `N2N_RISK_MODE=testing`, proxy socket failure or scan warnings do NOT block registration (fail-open for test suites).
   - **Inputs:** `N2N_RISK_MODE=testing`, port `:4000` unreachable.
   - **Assertions:**
     - Installer logs warning message `"Testing mode active: bypassing Model-Guard proxy socket requirement"`.
     - Registration proceeds and returns exit code `0`.

4. **`test_proxy_socket_timeout_handling()`**
   - **Description:** Verifies socket connection probe strictly enforces a 3-second timeout to prevent hanging installers on stalled proxy proxies.
   - **Inputs:** Mock socket server that accepts connections but delays response beyond 3.0 seconds.
   - **Assertions:**
     - Probe times out after exactly 3.0 seconds.
     - Handled as `proxy_unreachable`.

---

### Module 4: `tests/n2n/test_target_parity.py`
**Target Components:** `scripts/in2n-services.py`, `scripts/lib/mcp_compose.py`

#### Test Cases

1. **`test_confinement_directive_parity()`**
   - **Description:** Cross-checks that systemd user unit directives generated by `_mcp_unit_text()` match container security options generated in `docker-compose.mcp.yml` by `mcp_compose.py`.
   - **Directives Parity Mapping:**
     | Systemd Unit Directive | Docker Compose Container Security Option | Asserted Value |
     | :--- | :--- | :--- |
     | `NoNewPrivileges=yes` | `security_opt: ["no-new-privileges:true"]` | Strict equality |
     | `ProtectSystem=strict` | `read_only: true` | Strict equality |
     | `PrivateTmp=yes` | `tmpfs: ["/tmp"]` | Strict equality |
     | `InaccessiblePaths=-%h/.openclaw/.env` | Isolated file mount exclusion | Master `.env` omitted from volume mounts |

   - **Assertions:**
     - For every registered server, both target generators output equivalent security options.
     - Failure of either target to declare any of the required security options triggers assertion error.

2. **`test_env_mount_isolation_parity()`**
   - **Description:** Verifies both systemd units and docker-compose containers receive strictly sliced `.env.<mcp_name>` environment sources, never master `.env`.
   - **Assertions:**
     - Systemd unit `EnvironmentFile` points to `%h/.openclaw/config/env/.env.<mcp_name>`.
     - Docker compose service `env_file` points to `./config/env/.env.<mcp_name>`.
     - Neither configuration references `.env` directly.

3. **`test_single_source_of_truth_parity()`**
   - **Description:** Confirms both generators parse server list directly from `config/openclaw.json` `mcpServers` object, producing identical server sets.
   - **Inputs:** Configured `openclaw.json` with 5 servers.
   - **Assertions:**
     - `in2n-services.py` generates 5 `.service` unit files.
     - `mcp_compose.py` generates `docker-compose.mcp.yml` with 5 service definitions.
     - Service names in compose file strictly match systemd unit names.

---

## 3. Test Fixtures & Mocking Strategy

To ensure deterministic testing, fixtures will be defined in `tests/fixtures/mcp_installer/conftest.py`:

```python
import pytest
import socket
import threading
import json
from pathlib import Path

@pytest.fixture
def mock_openclaw_home(tmp_path, monkeypatch):
    """Provisions a isolated ~/.openclaw directory structure."""
    home = tmp_path / ".openclaw"
    config_dir = home / "config"
    env_dir = config_dir / "env"
    gait_dir = home / "n2n" / "gait"
    
    config_dir.mkdir(parents=True)
    env_dir.mkdir(parents=True)
    gait_dir.mkdir(parents=True)
    
    # Write master .env
    master_env = home / ".env"
    master_env.write_text("GITHUB_TOKEN=ghp_secret123\nSLACK_TOKEN=xoxb-secret456\n")
    master_env.chmod(0o600)
    
    # Write default openclaw.json
    openclaw_json = config_dir / "openclaw.json"
    openclaw_json.write_text(json.dumps({"mcpServers": {}}, indent=2))
    
    monkeypatch.setenv("HOME", str(tmp_path))
    return home

@pytest.fixture
def mock_defenseclaw_proxy():
    """Spawns a mock TCP socket listener on port 4000 for preflight testing."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("127.0.0.1", 4000))
    server_socket.listen(1)
    
    running = True
    def _listen():
        while running:
            try:
                server_socket.settimeout(0.5)
                client, _ = server_socket.accept()
                client.close()
            except socket.timeout:
                continue
            except Exception:
                break
                
    t = threading.Thread(target=_listen, daemon=True)
    t.start()
    yield "http://127.0.0.1:4000"
    running = False
    server_socket.close()
    t.join(timeout=1.0)
```

---

## 4. Execution & Verification Commands

```bash
# Run all new MCP installer and posture unit/parity tests
pytest tests/n2n/test_mcp_installer.py \
       tests/n2n/test_mcp_posture_dual_target.py \
       tests/n2n/test_model_guard_failclosed.py \
       tests/n2n/test_target_parity.py -v --tb=short

# Run with coverage report
pytest --cov=scripts/mcp-installer.py \
       --cov=scripts/register-mcps-with-defenseclaw.py \
       --cov=scripts/in2n-services.py \
       --cov=scripts/lib/mcp_compose.py \
       tests/n2n/test_mcp_*.py tests/n2n/test_target_parity.py
```

---

## 5. Definition of Done for Unit/Parity Layer

- [ ] All 15 unit and parity test cases implemented across the 4 specified test files in `tests/n2n/`.
- [ ] 100% pass rate under `pytest`.
- [ ] Zero lingering temp files or mutated system settings outside `tmp_path`.
- [ ] Confinement parity verified automatically on every build.
