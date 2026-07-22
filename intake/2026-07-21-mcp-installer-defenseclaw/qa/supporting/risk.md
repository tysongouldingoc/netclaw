# Risk & Regression Analysis — Selective MCP Installer & DefenseClaw Production Mode

> Authored by `qa-risk-analyst`. Detailed risk evaluation, blast radius assessment, load-bearing invariant analysis, and failure trap diagnosis for Feature 057 (`2026-07-21-mcp-installer-defenseclaw`).

- **Date**: 2026-07-21
- **Scope Source**: [change-brief.md](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/intake/2026-07-21-mcp-installer-defenseclaw/qa/change-brief.md)
- **Technical Plan**: [technical-plan.md](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/intake/2026-07-21-mcp-installer-defenseclaw/technical-plan.md)
- **Decision Log**: [decisions.md](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/intake/2026-07-21-mcp-installer-defenseclaw/decisions.md)

---

## 1. Risk Assessment Summary

- **Overall Risk Rating**: **HIGH / CRITICAL**
- **Implementation Priority**: **P0 (Blocker for Production Posture Enrolment)**
- **Primary Danger Vector**: Configuration drift between dynamic deployment targets (`systemd` vs `docker-compose`), secret leakage of master `.env` credentials to third-party MCP server processes, and false-positive posture reports masking degraded confinement.

---

## 2. Blast Radius Analysis

The selective MCP installer operates at the intersection of service orchestration, secret management, and security proxy gating. Its blast radius spans four distinct layers:

```
                          +-----------------------------------+
                          |     Installer CLI / Wizard        |
                          |     (scripts/mcp-installer.py)    |
                          +-----------------+-----------------+
                                            |
         +----------------------------------+----------------------------------+
         |                                  |                                  |
         v                                  v                                  v
+------------------+              +------------------+              +------------------+
| Security Gate    |              | Secret Slicing   |              | Config & Audit   |
| - Scan Engine    |              | - .env.<mcp>     |              | - openclaw.json  |
| - Proxy (:4000)  |              | - 0600 Perms     |              | - GAIT git log   |
+--------+---------+              +--------+---------+              +--------+---------+
         |                                  |                                  |
         +----------------------------------+----------------------------------+
                                            |
                                            v
                         +-----------------------------------+
                         |    Dual Runtime Orchestration     |
                         |  (systemd vs docker-compose)      |
                         +-----------------------------------+
```

### Direct Scope & Affected Systems
1. **Core Provisioning & TUI Wizard** ([mcp-installer.py](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/scripts/mcp-installer.py)): Single entry point for MCP selection, discovery of 27+ MCP servers in `mcp-servers/`, secret slicing, and posture calculation.
2. **Registration & Service Orchestration** ([register-mcps-with-defenseclaw.py](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/scripts/register-mcps-with-defenseclaw.py), [in2n-services.py](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/scripts/in2n-services.py), [mcp_compose.py](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/scripts/lib/mcp_compose.py)): Generator pipelines modifying host systemd user units and emitting `docker-compose.mcp.yml`.
3. **Master Configuration & Audit Trail** ([openclaw.json](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/config/openclaw.json), `~/.openclaw/n2n/gait/`): State mutations affecting all active agent-to-tool connections and append-only audit logging.

### Downstream System Risks
- **Traffic Interception Interruption**: If the Model-Guard proxy socket probe (:4000) fails or returns false status, active MCP traffic might bypass proxy inspection or fail completely across all 27+ integrations.
- **Credential Exposure**: Failure in secret slicing could expose master `~/.openclaw/.env` tokens (AWS keys, database passwords, API credentials) to unvetted MCP sub-processes.
- **Runtime Privilege Escalation**: Inconsistent container/unit security directives across targets could leave worker processes with write access to root filesystems or host kernel capabilities.

---

## 3. Invariants at Risk

### Invariant 1: Cross-Target Security Parity
- **Requirement**: Equal security confinement across `--target systemd` and `--target docker-compose`.
- **Systemd Constraints**: `NoNewPrivileges=yes`, `ProtectSystem=strict`, `PrivateTmp=yes`, `InaccessiblePaths=-%h/.openclaw/.env`.
- **Docker Compose Constraints**: `no-new-privileges:true`, `read_only: true`, `cap_drop: ["ALL"]`, `tmpfs: ["/tmp"]`, environment slice mount only.
- **Risk**: A security rule enforced under systemd (e.g. blocking access to `~/.openclaw/.env`) might be missing or relaxed in `docker-compose.mcp.yml` (e.g. mounting host volume `$HOME`), leading to target-dependent security vulnerabilities.

### Invariant 2: Environment Secret Isolation
- **Requirement**: Master `.env` (`~/.openclaw/.env`) MUST remain completely inaccessible to individual MCP servers. Each MCP server process only receives a isolated `.env.<mcp_name>` containing strictly required keys with file permissions `0600`.
- **Risk**: Key extraction logic accidentally includes unrequested environment variables or master file permissions default to world-readable (`0644`), enabling cross-server secret theft or credential harvesting.

### Invariant 3: Pre-Activation Security Scan & Fail-Closed Gate
- **Requirement**: Under `N2N_RISK_MODE=production`, activation of any MCP server requires:
  1. Static source code scan via [scan-all-mcp-source.py](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/scripts/scan-all-mcp-source.py) returning 0 HIGH/CRITICAL issues.
  2. Preflight TCP/HTTP probe to DefenseClaw Model-Guard proxy on port `:4000` succeeding.
- **Risk**: If the proxy is offline or scanning fails, an unchecked installer might fall back to unmonitored direct execution or swallow proxy errors, defeating DefenseClaw Production Mode.

### Invariant 4: Single Source of Truth & Audit Trail Integrity
- **Requirement**: `config/openclaw.json` (and `~/.openclaw/config/openclaw.json`) MUST be the sole authoritative source of truth for active/registered MCP servers. Every mutation must write an append-only GAIT git commit (`~/.openclaw/n2n/gait/`).
- **Risk**: Out-of-band editing or mismatched state between `openclaw.json`, systemd units, and Docker Compose active containers leads to "ghost services" running without registration or posture engine flagging state as `enforced` when runtime is actually drift-degraded.

---

## 4. "Ships Green But Broken" Traps

The following subtle failure modes can pass automated unit tests while failing catastrophically in live environments:

### Trap 1: Mock Socket False Positives & Proxy Protocol Mismatch
- **Mechanism**: Unit tests use standard `socket.connect(('localhost', 4000))` or basic HTTP mock (`mock_defenseclaw_proxy.py`). In production, port `:4000` might be open by another process (e.g., a leftover process or web server), causing the installer to report proxy availability even when DefenseClaw Model-Guard Go Proxy is NOT running or rejecting proxy protocol handshakes.
- **Impact**: Installer completes successfully under `N2N_RISK_MODE=production`, but MCP server traffic fails at runtime or bypasses Model-Guard governance.
- **Guard Rail**: Verification probe MUST perform an application-level health handshake (e.g., HTTP `GET /healthz` expecting `{"status": "ok", "service": "defenseclaw-proxy"}`) with explicit timeout handling, rather than relying solely on raw TCP port connectivity.

### Trap 2: Silent Degradation under WSL2 / Non-Systemd Environments
- **Mechanism**: Host systemd unit generator writes `NoNewPrivileges=yes` and `ProtectSystem=strict` into unit files. Unit tests check that file content string contains these lines. However, under WSL2 or lightweight containers without full cgroup v2 / kernel capabilities, systemd ignores or fails unit startup with error code `218/CAPABILITIES`.
- **Impact**: Test suite passes (string assertions match), but deployment fails silently or runs unconfined.
- **Guard Rail**: Posture calculator MUST query live kernel status (`systemctl --user is-active` and environment detection for WSL2) and explicitly set posture status to `production - DEGRADED (WSL2_kernel_limitation)` when host kernel capabilities cannot enforce unit security directives.

### Trap 3: NTFS / Cross-Platform Permission Fallthrough on `.env.<mcp>`
- **Mechanism**: Python `os.chmod(path, 0o600)` executes without raising errors on Windows NTFS file systems, but default Windows ACLs inherit permissions from parent directories (`config/env/`), leaving files readable by all local users.
- **Impact**: Secret isolation tests passing `os.stat(path).st_mode & 0o777 == 0o600` succeed on POSIX, but secrets remain world-readable on Windows deployments.
- **Guard Rail**: Secret slicing validator must test platform-specific ACL enforcement or verify parent folder containment policies to ensure non-POSIX filesystems maintain equivalent restriction.

### Trap 4: Partial Failure Split-Brain in Dynamic Multi-Server Selection
- **Mechanism**: Operator selects 5 MCP servers (`--select serverA,serverB,serverC,serverD,serverE`). During step 3, `serverC` fails pre-activation static security scan. If error handling cancels `serverC` but leaves `openclaw.json` updated with 5 servers, or leaves orphan systemd units for `serverA` and `serverB`, system state becomes inconsistent.
- **Impact**: `openclaw.json` single-source-of-truth is broken, partial deployments remain active without proxy authorization, and GAIT audit log contains incomplete transaction records.
- **Guard Rail**: Installer operations MUST execute within a atomic transaction envelope. Any single server failure MUST trigger full rollback of modified `openclaw.json` entries, temporary `.env.*` files, and generated service units/compose stacks.

### Trap 5: TTY Detection Bypass in Unattended / Pipeline Contexts
- **Mechanism**: If `scripts/mcp-installer.py` is invoked inside CI/CD or background subshell without a TTY, `sys.stdin.isatty()` returns `False`. If the argument fallback defaults to `--all` instead of aborting, unvetted MCP servers will be automatically provisioned without explicit operator consent.
- **Impact**: Accidental mass enablement of experimental or non-compliant MCP servers in automated pipelines.
- **Guard Rail**: In non-interactive mode (`isatty() == False`), missing `--select` or `--all` flags MUST strictly fail with exit code `1` and print usage instructions.

---

## 6. Severity & Priority Matrix

| Risk ID | Risk Category | Failure Scenario / Risk Description | Severity | Priority | Mitigation / Test Checkpoint |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **R-01** | Secret Isolation | Master `.env` accessed by container or unit due to path inheritance | **CRITICAL** | **P0** | Assert master `.env` path absent from unit environment & container volume binds |
| **R-02** | Security Gate | Installer proceeds when proxy `:4000` is offline or scan has HIGH findings | **CRITICAL** | **P0** | Negative test: mock proxy down & malicious code scan -> verify hard fail closed |
| **R-03** | Target Parity | Systemd & Docker Compose security options drift out of alignment | **HIGH** | **P1** | Automated AST / schema parity test comparing security directives between targets |
| **R-04** | State Integrity | `openclaw.json` state diverges from active runtime services | **HIGH** | **P1** | Posture calculation test verifying `DEGRADED (config_state_drift)` flag |
| **R-05** | Audit Logging | GAIT git commit omitted or fails silently during enrollment | **MEDIUM** | **P1** | Verify GAIT git log head commit after installer execution |
| **R-06** | Platform Limit | WSL2 kernel unit failure causes silent unconfined execution | **MEDIUM** | **P2** | WSL2 environment detection test verifying honest posture degradation |

---

## 7. Recommended QA Verification Strategy

To guarantee risk coverage across all surfaces, the QA test suite MUST enforce the following test layers:

1. **Parity Testing (`tests/n2n/test_target_parity.py`)**:
   - Compare security directives generated for `--target systemd` vs `--target docker-compose`.
   - Assert `no-new-privileges`, read-only root filesystems, temporary filesystem mounts (`/tmp`), and environment path masking are 100% structurally equivalent.

2. **Fail-Closed Chaos Injection (`tests/n2n/test_model_guard_failclosed.py`)**:
   - Test 1: Set `N2N_RISK_MODE=production`, ensure port `:4000` is closed -> assert exit code 1, 0 servers registered.
   - Test 2: Inject mock HIGH security vulnerability into MCP source code -> assert scan gate aborts installation and flags server as quarantined.

3. **Secret Slicing Isolation (`tests/n2n/test_mcp_installer.py`)**:
   - Create mock master `.env` with dummy credentials (`MASTER_SECRET=12345`, `MCP_FOO_KEY=abc`).
   - Run secret slicer for `mcp-foo` -> verify generated `.env.mcp-foo` contains ONLY `MCP_FOO_KEY`, file permissions are `0600`, and `MASTER_SECRET` is completely absent.

4. **Single Source of Truth & GAIT Audit Verification**:
   - Verify `config/openclaw.json` is updated atomically.
   - Assert `git log` under `~/.openclaw/n2n/gait/` contains structured JSON commit message matching the enrollment transaction.
