# QA Assessment — Selective MCP Installer & DefenseClaw Production Mode

> **Authored by**: `qa-strategist` for `team-qa`  
> **Intake ID**: `2026-07-21-mcp-installer-defenseclaw`  
> **Workspace**: `C:\Users\tyson\Documents\antigravity\amazing-babbage\netclaw`  
> **Date**: 2026-07-21  
> **Status**: COMPLETED / READY FOR TEST IMPLEMENTATION  

---

## 1. Executive Summary & Verdict

### **Coverage Verdict: GAPPED (New Files / Scripts Un-tested)**

The **Selective MCP Server Installer & DefenseClaw Production Mode** feature introduces critical system orchestration, security proxy preflight gating, least-privilege secret slicing, dynamic posture calculation, and dual-runtime deployment targets (`--target systemd` and `--target docker-compose`). 

While existing posture calculation (`tests/n2n/test_posture.py`) and fail-closed gates (`tests/n2n/test_controls_failclosed.py`) possess baseline tests (~75–80% coverage on core BGP federation modules), the newly added installer script (`scripts/mcp-installer.py`), Docker Compose stack generator (`scripts/lib/mcp_compose.py`), and selective registration options in `scripts/register-mcps-with-defenseclaw.py` currently have **0% direct test coverage**.

Executing the change in production without the required 4-suite test expansion introduces severe security and operational risks, including false-positive posture reports, secret exposure via un-sliced environment files, and silent confinement drift between `systemd` and `docker-compose` targets.

---

## 2. Test Debt Diagnosis & Systemic Root Causes

### 2.1 Technical Test Debt Breakdown
1. **Platform Import Hard Block (`fcntl`)**: Running `pytest` across the full test suite fails during collection under Windows environments because `mcp-servers/protocol-mcp/bgp/tun.py` unconditionally imports `fcntl` (a POSIX-only C extension). This prevents full-suite regression runs on non-Linux developer workstations.
2. **Zero Coverage on Primary Installer Pipeline**:
   - `scripts/mcp-installer.py`: 0% test coverage.
   - `scripts/lib/mcp_compose.py`: 0% test coverage.
   - `scripts/register-mcps-with-defenseclaw.py`: 0% direct script coverage.
3. **Absence of Cross-Target Confinement Parity Verification**: No automated tests exist to verify that container security options in `docker-compose.mcp.yml` (`no-new-privileges:true`, `read_only: true`, `cap_drop: ["ALL"]`, `tmpfs: ["/tmp"]`) maintain 100% equivalence with host systemd user unit directives (`NoNewPrivileges=yes`, `ProtectSystem=strict`, `PrivateTmp=yes`, `InaccessiblePaths=-%h/.openclaw/.env`).
4. **Un-tested Preflight Proxy Socket Gate on Port `:4000`**: The fail-closed socket check (`verify_model_guard_proxy(port=4000)`) under `N2N_RISK_MODE=production` lacks automated chaos testing for port unreachable and socket timeout conditions.

### 2.2 Systemic Root Causes
- **Orchestration Expansion Ahead of Test Tooling**: Development of selective multi-target orchestration (`systemd` + `docker-compose`) preceded the creation of mock test fixtures for low-level OS interactions (sockets, systemd units, Docker Compose files).
- **Platform-Dependent Module Dependencies**: Python modules importing POSIX kernel interfaces (`fcntl`) were included without platform isolation guards, creating platform-fragile test suites.
- **Asymmetric Feature Growth**: Features were added to CLI scripts directly without corresponding TDD specs or mock-based unit tests.

---

## 3. High-Risk "Ships Green But Broken" Failure Modes

| Trap ID | Risk Category | Mechanism / Failure Scenario | Impact |
| :--- | :--- | :--- | :--- |
| **TRAP-1** | **Proxy Socket Protocol Mismatch** | `socket.connect(('localhost', 4000))` returns `True` if any local process binds port 4000, even if DefenseClaw Model-Guard Go Proxy is offline or misconfigured. | Uninspected MCP server traffic bypasses security proxy in production mode. |
| **TRAP-2** | **WSL2 / Non-Systemd Confinement Fallthrough** | Systemd unit files containing `NoNewPrivileges=yes` pass string assertions in tests, but host systemd init under WSL2 ignores or fails capability directives silently. | Worker processes execute unconfined while posture calculation false-reports `production - enforced`. |
| **TRAP-3** | **Secret Slicing Permission Bypass on NTFS** | `os.chmod(path, 0o600)` executes without exception on Windows NTFS, but default ACL inheritance leaves `.env.<mcp>` readable to local users. | Master `.env` secrets or per-server secrets exposed to unauthorized processes. |
| **TRAP-4** | **Partial Selection Atomic Rollback Failure** | Partial failure during a multi-server install (e.g. 1 of 5 servers fails static scan) leaves orphan systemd units or partially mutated `openclaw.json`. | Split-brain state between authoritative config and active runtime services. |

---

## 4. Durable Coverage Plan: Must-Add-Now 4 Test Suites

To eliminate coverage gaps and resolve test debt, the following **4 new test suites** and **1 fixture module** MUST be implemented immediately:

```
tests/
├── fixtures/
│   └── mcp_installer/
│       ├── mock_mcp_servers/           # Clean & vulnerable synthetic MCP packages
│       ├── mock_master_env             # Multi-secret master .env fixture
│       ├── mock_openclaw_json          # Master schema fixture
│       └── mock_defenseclaw_proxy.py   # Async TCP/HTTP stub for port :4000
└── n2n/
    ├── test_mcp_installer.py           # Installer CLI selection, openclaw.json atomic updates, secret slicing & 0600 perms
    ├── test_mcp_posture_dual_target.py # Posture evaluation across systemd vs docker-compose targets & WSL2 degradation
    ├── test_model_guard_failclosed.py  # Fail-closed preflight proxy probe (:4000) & static scan aborts
    └── test_target_parity.py           # AST / schema parity comparison of security directives across targets
```

### Summary of Required Test Suites:

1. **`tests/n2n/test_mcp_installer.py`**
   - Tests CLI `--select` / `--all` filtering, non-interactive TTY detachment fail-fast (exit code 1).
   - Tests atomic mutation and rollback of `~/.openclaw/config/openclaw.json`.
   - Asserts secret slicing generates `.env.<mcp_name>` with strict `0600` permissions (`-rw-------`) and zero master secret leak.

2. **`tests/n2n/test_mcp_posture_dual_target.py`**
   - Verifies posture engine returns `production — enforced` when all controls pass across systemd and docker-compose targets.
   - Tests posture degradation (`production — DEGRADED (<missing_control>)`).
   - Asserts WSL2 kernel capability limitations degrade posture to `production — DEGRADED (WSL2_kernel_limitation)` gracefully.

3. **`tests/n2n/test_model_guard_failclosed.py`**
   - Tests `N2N_RISK_MODE=production` fail-closed abort (exit code 1) when Model-Guard proxy on port `:4000` is offline or times out (3.0s threshold).
   - Tests static scan gate aborting setup when HIGH/CRITICAL vulnerability detected in `scan-all-mcp-source.py`.
   - Verifies fail-open bypass behavior strictly under `N2N_RISK_MODE=testing`.

4. **`tests/n2n/test_target_parity.py`**
   - Asserts 100% structural parity between systemd directives (`NoNewPrivileges=yes`, `ProtectSystem=strict`, `PrivateTmp=yes`, `InaccessiblePaths=-%h/.openclaw/.env`) and Docker Compose container security options (`no-new-privileges:true`, `read_only: true`, `cap_drop: ["ALL"]`, `tmpfs: ["/tmp"]`).

---

## 5. Implementation Roadmap & QA Recommendations

1. **Immediate Platform Guard in `conftest.py`**: Add a global `sys.modules['fcntl']` stub fixture to `conftest.py` allowing Windows test runners to execute `pytest` cleanly.
2. **Atomic Execution Envelope**: Implement transactional rollback in `scripts/mcp-installer.py` so partial install failures restore `openclaw.json` and prune temporary `.env.*` files.
3. **Application-Level Proxy Handshake**: Upgrade `verify_model_guard_proxy(port=4000)` from raw TCP socket probe to an HTTP `GET /healthz` check to prevent false positives from generic listening sockets.

---

## 6. Definition of Done

- [ ] All 4 test suites created under `tests/n2n/`.
- [ ] 100% pass rate under `pytest`.
- [ ] `conftest.py` updated with cross-platform `fcntl` stub.
- [ ] Confinement parity and secret isolation verified automatically on every build.
