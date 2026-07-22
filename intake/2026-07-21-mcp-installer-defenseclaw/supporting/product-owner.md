# Product Owner Findings — MCP Installer with DefenseClaw Production Mode

- **Intake ID**: `2026-07-21-mcp-installer-defenseclaw`
- **Role**: `intake-product-owner`
- **Target Feature**: Feature 057 - N2N Production Posture & Selective MCP Server Installer
- **Workspace**: `C:\Users\tyson\Documents\antigravity\amazing-babbage\netclaw`
- **Date**: 2026-07-21

---

## 1. Value & Business Intent
- **Core Value Proposition**: Enables operators to selectively provision any subset of NetClaw's 27+ MCP servers while enforcing strict, un-bypassable DefenseClaw production posture (`N2N_RISK_MODE=production`).
- **Operational Flexibility**: Operators can customize their deployment footprint (minimizing attack surface and resource utilization) across two runtime targets: containerized Docker Compose stacks and native host systemd units.
- **Durable Posture Integrity**: Prevents security drift by mandating pre-activation component scanning via DefenseClaw, fail-closed Model-Guard proxying (`:4000`), sliced environment secrets per server, and append-only GAIT audit tracking.

---

## 2. Scope Verification

### In-Scope:
1. **Selective MCP Installer CLI / Wizard**:
   - `scripts/mcp-installer.py` (and CLI wrapper) supporting interactive prompt selection and non-interactive CLI flags (`--select`, `--all`, `--target`, `--mode`).
   - Registration updates in `config/openclaw.json` (and `~/.openclaw/config/openclaw.json`).
2. **Dual-Runtime Generation Target (DEC-001)**:
   - `--target docker-compose`: Generates a hardened `docker-compose.yml` (specifying `security_opt: [no-new-privileges:true]`, read-only root filesystems, sliced environment variables, and proxy network links).
   - `--target systemd`: Integrates with `scripts/in2n-services.py` to generate host-confined systemd user service units (`NoNewPrivileges`, `ProtectSystem=strict`, private `/tmp`).
3. **DefenseClaw Production Gate Integration**:
   - Automated pre-activation scanning via `scripts/scan-all-mcp-source.py` / `register-mcps-with-defenseclaw.py`. Aborts activation if critical security findings arise.
   - Enforced fail-closed routing through DefenseClaw Model-Guard proxy (`:4000`).
4. **Least-Privilege Secret Slicing**:
   - Extraction of per-MCP environment variables into isolated `.env.<mcp_name>` files, ensuring master `.env` remains hidden from sandbox environments.
5. **GAIT Audit Log Registration**:
   - Append-only logging of all install, enrollment, removal, and quarantine operations to `~/.openclaw/n2n/gait/`.
6. **Dynamic Posture Calculation & Reporting**:
   - Reporting posture states (`testing`, `production - enforced`, `production - DEGRADED (<reasons>)`) based on runtime capability and control status.

### Out-of-Scope:
- Modifying underlying MCP server source code within `mcp-servers/`.
- Developing new DefenseClaw proxy binaries or Go proxy internal logic (consuming existing `:4000` contract).
- Replacing host Linux kernel confinement on systems where native systemd is targeted.

---

## 3. Acceptance Criteria (Testable Done When...)

1. **Selective Installation Wizard & CLI**:
   - [ ] Running `python scripts/mcp-installer.py --list` displays all available MCP servers from `mcp-servers/` with current registration status.
   - [ ] Running `mcp-installer.py` interactively or with `--select gnmi-mcp,netbox-mcp` correctly registers only specified MCP servers in `openclaw.json`.
2. **Dual-Runtime Provisioning Output**:
   - [ ] When invoked with `--target docker-compose`, the utility generates a valid `docker-compose.yml` containing hardened profiles for selected MCP servers.
   - [ ] When invoked with `--target systemd`, the utility generates systemd user service units with `NoNewPrivileges=yes`, `ProtectSystem=strict`, and `Restart=always`.
3. **DefenseClaw Pre-Activation Gate**:
   - [ ] In `N2N_RISK_MODE=production`, selected MCP servers are scanned by `scripts/scan-all-mcp-source.py` prior to activation. Any un-remediated high/critical scan result halts activation.
   - [ ] Activated MCP servers are configured to route Model I/O strictly through `:4000` (DefenseClaw Model-Guard proxy) fail-closed.
4. **Least-Privilege Environment Slicing**:
   - [ ] Each installed MCP server receives a dedicated `.env.<mcp_name>` containing only its explicit key dependencies. The master `.env` is unreadable within the MCP server process context.
5. **GAIT Audit Log Trail**:
   - [ ] Every install, uninstall, or configuration mutation writes a verified commit to `~/.openclaw/n2n/gait/`.
6. **Honest Posture Reporting**:
   - [ ] A posture status command returns `production - enforced` when all 7 controls are satisfied, or `production - DEGRADED (<missing_controls>)` if any containment or guard control is incomplete.

---

## 4. Priority & Impact
- **Priority**: High (P1) — Critical for production deployment readiness of NetClaw Feature 057.
- **Security Impact**: Eliminates over-privileged secret exposure, enforces mandatory pre-activation scanning, and guarantees model proxy inspection across containerized and native Linux deployments.
- **Operational Impact**: Simplifies multi-server lifecycle management, allowing operators to deploy tailored MCP stacks without manual configuration edits.

---

## 5. Stakeholder & Product Questions

1. **CI/CD TTY Auto-Detection**:
   - *Question*: Should `mcp-installer.py` automatically infer non-interactive mode when stdin is not attached to a TTY?
   - *Recommendation*: Yes, auto-detect TTY and require explicit flags in batch contexts.
2. **Handling Un-configured Secrets**:
   - *Question*: What is the workflow when an operator selects an MCP server with missing environment variables in the master `.env`?
   - *Recommendation*: Prompt for missing values interactively or write a `.env.<mcp_name>.template` and tag registration as `degraded-pending-secrets`.
