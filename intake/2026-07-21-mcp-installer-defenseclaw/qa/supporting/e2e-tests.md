# E2E & Integration Test Architecture — Selective MCP Installer & DefenseClaw Production Mode

**Intake ID**: `2026-07-21-mcp-installer-defenseclaw`  
**Target Feature**: Feature 057 — Selective MCP Server Installer & DefenseClaw Production Mode  
**Workspace**: `C:\Users\tyson\Documents\antigravity\amazing-babbage\netclaw`  
**Author**: E2E / API Test Architect (`qa-e2e-architect`)  
**Date**: 2026-07-21  
**Status**: APPROVED / READY FOR VERIFICATION  

---

## 1. Overview & E2E Scope

This document specifies the Integration and End-to-End (E2E) testing framework for the Selective MCP Installer CLI utility (`scripts/mcp-installer.py`), dual runtime target generators (`--target docker-compose` and `--target systemd`), DefenseClaw preflight proxy gates, secret slicing isolation, and GAIT git audit logging.

### Primary E2E Test Vectors
1. **CLI Non-Interactive Flag & TUI Flow**: Verification of non-interactive parameter passing (`--select`, `--target`, `--mode`) and interactive wizard fallback logic.
2. **Docker Compose Target Validation**: Validation of generated `docker-compose.mcp.yml` using `docker compose config` and security profile inspection.
3. **Systemd User Unit Syntax & Confinement Validation**: Syntax verification of generated `.service` unit files via `systemd-analyze verify` (or mock unit parser fallback) and kernel confinement directive assertions.
4. **GAIT Append-Only Git Trail Verification**: End-to-end verification of git commit logging in `~/.openclaw/n2n/gait/`.
5. **Fail-Closed Security Gate Verification**: Verification of pre-activation static scan enforcement and Model-Guard proxy socket check (:4000) under `N2N_RISK_MODE=production`.
6. **Least-Privilege Secret Slicing**: Verification that sliced `.env.<mcp_name>` files are created with `0600` permissions while master `.env` remains protected.

---

## 2. Test Architecture & Environment Isolation

All integration and E2E tests must execute in isolated temporary environments using `pytest` fixtures. Real system states (`~/.openclaw/` and systemd units) must be sandboxed to avoid polluting host environments.

```mermaid
flowchart TD
    subgraph Test Runner (Pytest)
        A["Test Setup / Fixture Isolation"] --> B["CLI Execution (mcp-installer.py)"]
        B --> C1["Docker Compose Target"]
        B --> C2["Systemd Target"]
        B --> C3["GAIT Audit Logging"]
        B --> C4["Fail-Closed Security Gate"]
    end
    C1 --> D1["docker compose config --quiet"]
    C2 --> D2["systemd-analyze verify / Unit Parser"]
    C3 --> D3["git -C <tmp_gait> log --oneline"]
    C4 --> D4["Mock Model-Guard Proxy (:4000)"]
```

### Environment Isolation Rules
- **Temporary Directories (`tmp_path`)**: Override `OPENCLAW_HOME` and `GAIT_DIR` environment variables to point to test-scoped `tmp_path`.
- **Mock Proxy Socket**: Use `tests/fixtures/mcp_installer/mock_defenseclaw_proxy.py` to simulate online/offline state of DefenseClaw proxy on port `:4000`.
- **Systemd & Docker CLI Fallbacks**: When running in environments lacking full Docker daemon or Systemd init (e.g. Windows/CI runner), fallback gracefully to structural AST/YAML schema parsers while asserting full syntax compliance.

---

## 3. End-to-End Test Specifications

### Test Suite 1: CLI Non-Interactive & Wizard Selection (`E2E-001`)

**Target Script**: `scripts/mcp-installer.py`  
**Test Objective**: Ensure non-interactive execution requires explicit `--select` or `--all` flags, succeeds with selected MCP servers, and outputs proper JSON/structured logs.

#### Test Cases
* **`E2E-001-1`: Non-Interactive Missing Flags Fail-Fast**
  - *Command*: `python scripts/mcp-installer.py --target docker-compose` (with TTY detached)
  - *Expected Outcome*: Exit code `1`. Output error: `Non-interactive execution requires --select or --all`.
* **`E2E-001-2`: Single Server Selection Execution**
  - *Command*: `python scripts/mcp-installer.py --select gnmi-mcp --target docker-compose --dry-run`
  - *Expected Outcome*: Exit code `0`. Plan output indicates `gnmi-mcp` staged, security scan queued, target set to `docker-compose`.
* **`E2E-001-3`: Multiple Server Selection with Exclusions**
  - *Command*: `python scripts/mcp-installer.py --all --exclude batfish-mcp --target systemd --dry-run`
  - *Expected Outcome*: Exit code `0`. All discovered servers staged except `batfish-mcp`.

---

### Test Suite 2: Docker Compose Target Provisioning & Syntax Validation (`E2E-002`)

**Target Generator**: `scripts/lib/mcp_compose.py` / `scripts/mcp-installer.py --target docker-compose`  
**Test Objective**: Verify generated `docker-compose.mcp.yml` conforms to OCI compose specs, passes `docker compose config`, and includes mandatory security constraints.

#### Test Cases
* **`E2E-002-1`: Compose File Syntax Verification via `docker compose config`**
  - *Command*: `docker compose -f <tmp_path>/docker-compose.mcp.yml config --quiet`
  - *Expected Outcome*: Exit code `0` (valid YAML structure and schema).
* **`E2E-002-2`: Container Security Directives Assertion**
  - *Validation Rules*:
    - `security_opt`: MUST contain `"no-new-privileges:true"`.
    - `read_only`: MUST be `true`.
    - `cap_drop`: MUST contain `["ALL"]`.
    - `tmpfs`: MUST mount `["/tmp"]`.
    - `env_file`: MUST point exclusively to `config/env/.env.<mcp_name>`.

```python
def test_docker_compose_target_validation(tmp_path, monkeypatch):
    compose_file = tmp_path / "docker-compose.mcp.yml"
    # Invoke generator
    cmd = [
        sys.executable, "scripts/mcp-installer.py",
        "--select", "gnmi-mcp",
        "--target", "docker-compose",
        "--output-file", str(compose_file)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    
    # Run docker compose config check if docker is present
    if shutil.which("docker"):
        check_res = subprocess.run(["docker", "compose", "-f", str(compose_file), "config", "--quiet"])
        assert check_res.returncode == 0
    
    # Structural assertion fallback
    with open(compose_file) as f:
        data = yaml.safe_load(f)
    service = data["services"]["gnmi-mcp"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["read_only"] is True
    assert "ALL" in service["cap_drop"]
```

---

### Test Suite 3: Systemd User Service Generation & Unit Syntax Validation (`E2E-003`)

**Target Generator**: `scripts/in2n-services.py` / `scripts/mcp-installer.py --target systemd`  
**Test Objective**: Verify generated user systemd service unit files syntax via `systemd-analyze verify` or AST parser and validate kernel confinement directives.

#### Test Cases
* **`E2E-003-1`: Systemd Unit File Syntax Verification**
  - *Command*: `systemd-analyze verify <tmp_path>/openclaw-mcp-gnmi-mcp.service`
  - *Expected Outcome*: Exit code `0` (no syntax error or undefined key errors).
* **`E2E-003-2`: Kernel Confinement Directives Assertion**
  - *Required Unit Directives*:
    - `NoNewPrivileges=yes`
    - `ProtectSystem=strict`
    - `PrivateTmp=yes`
    - `InaccessiblePaths=-%h/.openclaw/.env`
    - `EnvironmentFile=<tmp_path>/config/env/.env.gnmi-mcp`

```python
def test_systemd_unit_confinement_directives(tmp_path):
    unit_file = tmp_path / "openclaw-mcp-gnmi-mcp.service"
    # Invoke installer with systemd target
    # Parse generated unit file
    content = unit_file.read_text()
    assert "NoNewPrivileges=yes" in content
    assert "ProtectSystem=strict" in content
    assert "PrivateTmp=yes" in content
    assert "InaccessiblePaths=-%h/.openclaw/.env" in content
```

---

### Test Suite 4: GAIT Append-Only Git Trail Verification (`E2E-004`)

**Target Module**: `bgp.federation.gait` / `~/.openclaw/n2n/gait/`  
**Test Objective**: Assert every installer action creates an attributable append-only commit in GAIT git repository with JSON metadata.

#### Test Cases
* **`E2E-004-1`: Single Server Install Append Commit**
  - *Command*: `git -C <tmp_gait> log -n 1 --oneline`
  - *Expected Outcome*: Commit log displays `enrollment gnmi-mcp by operator`.
* **`E2E-004-2`: Append-Only Trail Immutability**
  - *Validation*: Performing 3 consecutive install/uninstall actions creates 3 distinct commits in linear history; previous commit SHAs remain unchanged.

```python
def test_gait_audit_logging_e2e(tmp_path):
    gait_dir = tmp_path / "gait"
    env = os.environ.copy()
    env["GAIT_DIR"] = str(gait_dir)
    
    # Run installer
    subprocess.run([sys.executable, "scripts/mcp-installer.py", "--select", "gnmi-mcp", "--target", "docker-compose"], env=env, check=True)
    
    # Verify git log
    log_out = subprocess.check_output(["git", "-C", str(gait_dir), "log", "--oneline"], text=True)
    assert "enrollment gnmi-mcp" in log_out
```

---

### Test Suite 5: Fail-Closed Preflight Proxy & Security Scan Gate (`E2E-005`)

**Target Layer**: `scripts/register-mcps-with-defenseclaw.py` & Model-Guard Proxy  
**Test Objective**: Verify installer aborts fail-closed under `N2N_RISK_MODE=production` if proxy on `:4000` is offline or static scan fails.

#### Test Cases
* **`E2E-005-1`: Proxy Down -> Abort Setup**
  - *Conditions*: Proxy on `:4000` offline, `N2N_RISK_MODE=production`.
  - *Expected Outcome*: Exit code `1`. Output message: `Model-Guard proxy (:4000) unreachable. Aborting setup under N2N_RISK_MODE=production.`
* **`E2E-005-2`: Static Scan Vulnerability -> Quarantine**
  - *Conditions*: Mock MCP server contains static security finding.
  - *Expected Outcome*: Server flagged as `quarantined`, enrollment skipped.

---

### Test Suite 6: Secret Slicing & Permission Isolation (`E2E-006`)

**Target Layer**: `scripts/mcp-installer.py` (Secret Slicing Engine)  
**Test Objective**: Verify generated per-MCP `.env` files contain only required keys and enforce `0600` permissions.

#### Test Cases
* **`E2E-006-1`: File Mode Permissions Check (`0600`)**
  - *Expected Outcome*: `oct(os.stat(env_file).st_mode)[-3:] == "600"`.
* **`E2E-006-2`: Key Isolation Assertion**
  - *Expected Outcome*: `.env.gnmi-mcp` contains `GNMI_PORT` and `GNMI_CREDS`, but DOES NOT contain `BATFISH_API_KEY` or master keys.

---

## 4. Test Execution Matrix

| Test ID | Test Category | Target Component | Command / Tool | Success Criteria |
| :--- | :--- | :--- | :--- | :--- |
| **E2E-001** | CLI Flow | `scripts/mcp-installer.py` | Pytest / Subprocess | Proper flag handling & non-interactive TTY check |
| **E2E-002** | Docker Compose | `scripts/lib/mcp_compose.py` | `docker compose config` | Exit code 0, security opts present (`no-new-privileges`, `read_only`) |
| **E2E-003** | Systemd Target | `scripts/in2n-services.py` | `systemd-analyze verify` | Exit code 0, kernel confinement directives present |
| **E2E-004** | GAIT Audit | `bgp.federation.gait` | `git log --oneline` | Append-only commit created with JSON audit record |
| **E2E-005** | Security Gate | DefenseClaw Proxy (:4000) | Socket Probe | Fail-closed exit code 1 when proxy offline in production mode |
| **E2E-006** | Secret Slicing | `config/env/.env.*` | `os.stat` / File IO | Mode `0600`, zero master secret leakage |

---

## 5. Definition of Done & Verification Checklist

- [x] Test specifications written for all 4 required E2E flows (CLI flags, Docker Compose, Systemd units, GAIT audit logging).
- [x] Validation commands defined for runtime targets (`docker compose config` and `systemd-analyze verify`).
- [x] Environment isolation strategy established for test runners.
- [x] Fail-closed and least-privilege security assertions specified.
- [x] Output file written to `C:\Users\tyson\Documents\antigravity\amazing-babbage\netclaw\intake\2026-07-21-mcp-installer-defenseclaw\qa\supporting\e2e-tests.md`.
