# Intake Request Brief: Custom Installer for MCP Servers with DefenseClaw Production Mode

**Intake ID**: `2026-07-21-mcp-installer-defenseclaw`  
**Target Feature**: Feature 057 - N2N Production Posture & Selective MCP Server Installer  
**Workspace**: `C:\Users\tyson\Documents\antigravity\amazing-babbage\netclaw`  
**Date**: 2026-07-21  
**Intake Clerk**: `intake-triage`  

---

## 1. Raw Ask Summary
The client requests a custom installer for NetClaw MCP servers that allows operators to select which MCP servers to install/enable or skip. The installer must support deployment via Docker Compose while fully implementing **DefenseClaw Production Mode** (`N2N_RISK_MODE=production`) — enforced, honest, and durable (Feature 057).

The production posture relies on 7 core security/runtime controls:
1. **Member Sandbox**: Host-level kernel confinement via systemd units (`NoNewPrivileges`, `ProtectSystem=strict`, hidden master `.env`, private `/tmp`).
2. **Model-Guard**: DefenseClaw LLM guardrail proxy (`:4000`) for prompt/response inspection & pre-execution component scanning. Fail-closed on guard unavailability.
3. **Audit**: GAIT append-only git trail in `~/.openclaw/n2n/gait/` cross-referenced with SQLite.
4. **Least-Privilege Secrets**: Sliced per-member `.env` configs hiding the master `.env`.
5. **Honest Posture**: Posture reporting (`testing`, `production - enforced`, or `production - DEGRADED (<missing_controls>)`). Containment gaps block execution; audit gaps flag degraded unless `N2N_STRICT_ALL=1`.
6. **Durable Runtime**: Mesh daemon and always-on members managed via `scripts/in2n-services.py` systemd user services (`Restart=always`).
7. **A2A Cards**: Peer cards advertising risk posture and LLM security/reasoning tier.

---

## 2. Restated Technical Objectives
1. **Selective MCP Installer Utility**:
   - Develop an interactive CLI wizard & flag-based script (`scripts/mcp-installer.py` / `scripts/mcp-installer.sh`) allowing users to inspect the 27+ MCP servers in `mcp-servers/` and toggle individual installations.
   - Automatically update `openclaw.json` registrations and per-member environments.
2. **Docker Compose & Systemd Dual Target Provisioning**:
   - Generate production-grade `docker-compose.yml` stack files for containerized MCP server execution and DefenseClaw proxy integration.
   - Integrate with `scripts/in2n-services.py` for host-confined systemd service generation where native Linux kernel confinement is targeted.
3. **DefenseClaw Production Mode Enforcer**:
   - Enforce `N2N_RISK_MODE=production` across all selected MCP servers.
   - Integrate `scripts/register-mcps-with-defenseclaw.py` and `scripts/scan-all-mcp-source.py` to enforce component scanning prior to service activation.
   - Enforce fail-closed proxy routing (:4000) and strict secret slicing.
4. **Honest Posture & GAIT Audit Integration**:
   - Record all install, enrollment, removal, and quarantine operations in GAIT append-only logs.
   - Calculate and publish dynamic posture status (`production - enforced` vs `production - DEGRADED`).

---

## 3. Surfaces Touched
- **MCP Server Repository**: `mcp-servers/` (27 local server directories + `mcp-servers/README.md`)
- **Installation & Setup Scripts**:
  - `scripts/install.sh`
  - `scripts/setup.sh`
  - `scripts/register-mcps-with-defenseclaw.py`
  - `scripts/in2n-services.py`
  - `scripts/defenseclaw-enable.sh`
  - *New*: `scripts/mcp-installer.py` (or shell equivalent)
- **Configuration Files**:
  - `config/openclaw.json` / `~/.openclaw/config/openclaw.json`
  - `.env.example` & per-member `.env.<member_name>` secret slices
- **Container & Service Orchestration**:
  - `docker-compose.yml` (new or templated Compose stack for selective MCPs)
  - `scripts/systemd/` unit templates
- **Audit & Security Systems**:
  - `~/.openclaw/n2n/gait/` (GAIT git log trail)
  - DefenseClaw Go Proxy (`:4000`) integration

---

## 4. Provisional Request Type
**Feature / Architectural Expansion** (Feature 057: N2N Production Posture & Selective MCP Installer with DefenseClaw Integration)

---

## 5. Explicit Acceptance Signals
- [ ] Operator can run an installer script and select specific MCP servers to install/enable or bypass.
- [ ] Installer can output a valid `docker-compose.yml` stack and/or host `systemd` user service units.
- [ ] Under `N2N_RISK_MODE=production`, all selected MCP servers undergo DefenseClaw source scanning and register fail-closed through Model-Guard (`:4000`).
- [ ] Each installed MCP server receives only its own sliced `.env` config file without access to the master `.env`.
- [ ] GAIT append-only audit trail records every MCP enrollment/installation event.
- [ ] Posture calculation correctly reports `production - DEGRADED` if any containment or guard control is missing or disabled.

---

## 6. Ambiguity Analysis (BLOCKING vs Non-Blocking)

### 🟢 Resolved Ambiguities

1. **Host-Level Kernel Confinement vs Docker Compose Deployment Model** (Resolved via DEC-001):
   - *Decision*: Option A — Dual Runtime Target Support.
   - *Implementation*: Installer supports both `--target docker-compose` (hardened container profile) and `--target systemd` (host Linux kernel confinement). Posture assessment dynamically checks target capabilities.

---

### 🟡 Non-Blocking Ambiguities

2. **Installer Interface Mode**:
   - *Ambiguity*: Should the custom installer be an interactive terminal UI (Python `curses`/`inquirer`), a CLI script with flags (`--enable gnmi-mcp,netbox-mcp`), or both?
   - *Proposed Default*: Implement `scripts/mcp-installer.py` supporting both interactive prompt selection and non-interactive CLI flags (`--select`, `--all`, `--target`).

3. **Pre-scanned vs Real-time DefenseClaw Scanning**:
   - *Ambiguity*: `DefenseClawMCPScan.md` records 42 clean MCPs. Should the installer bypass scanning for pre-verified servers?
   - *Proposed Default*: In `N2N_RISK_MODE=production`, real-time scan via `defenseclaw mcp set` / `scripts/scan-all-mcp-source.py` MUST execute prior to enabling the server, failing closed if any severity warnings arise.

4. **Secret Isolation Mechanics**:
   - *Ambiguity*: How are per-integration `.env` slices extracted from the master environment?
   - *Proposed Default*: Maintain a schema mapping required environment variables per MCP server and write isolated `.env.<mcp-name>` files during installation.

---

## 7. Product-Fork Decisions (For `decisions.md`)

- **DEC-001: Dual-Runtime Target Support (DECIDED)**:
  The installer will support both `--target systemd` (generating host-confined systemd units via `in2n-services.py`) and `--target docker-compose` (generating a custom `docker-compose.yml` with hardened container profiles).
- **Decision 2: Strict Fail-Closed Pre-Activation Gate**:
  If `N2N_RISK_MODE=production` is set, the installer will abort activation of any MCP server that fails DefenseClaw scanning or lacks model-guard connectivity.
- **Decision 3: Honest Posture Fallback**:
  If Docker Compose deployment is chosen without host systemd unit confinement, posture engine will evaluate container security options to determine if containment meets `production - enforced` or reverts to `production - DEGRADED`.

---

## 8. Triage Verdict
**Verdict**: `READY` (DEC-001 resolved; ready for parallel evaluation).
