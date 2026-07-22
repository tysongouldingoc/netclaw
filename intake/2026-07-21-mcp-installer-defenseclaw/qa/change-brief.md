# Change Brief — Selective MCP Installer & DefenseClaw Production Mode

> Authored by `qa-triage`. The single normalized statement of *what we just changed*, before any coverage evaluation.

- **Date:** 2026-07-21
- **Scope source:** intake-handoff
- **Intake link:** [technical-plan.md](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/intake/2026-07-21-mcp-installer-defenseclaw/technical-plan.md) | [request-brief.md](file:///C:/Users/tyson/Documents/antigravity/amazing-babbage/netclaw/intake/2026-07-21-mcp-installer-defenseclaw/request-brief.md)

---

## Change summary
Provision a selective MCP server installer CLI and interactive wizard (`scripts/mcp-installer.py`) enabling operators to select, enable, or skip any subset of NetClaw's 27+ MCP servers. The installer supports dual runtime targets (`--target systemd` for host systemd user unit confinement and `--target docker-compose` for hardened container stacks per DEC-001) while enforcing DefenseClaw Production Mode (`N2N_RISK_MODE=production`), fail-closed proxy preflight routing (:4000), pre-activation static source code scanning, least-privilege `.env` secret slicing (`0600` permissions), GAIT append-only audit logging (`~/.openclaw/n2n/gait/`), and dynamic posture calculation.

---

## Changed files (by layer)

### Core Installer Utility & CLI Layer
- `scripts/mcp-installer.py` *(New File)* — Unified CLI/TUI wizard, server discovery module (`mcp-servers/*/`), secret slicing engine, pre-activation security scan and proxy preflight orchestrator, target generator dispatch, GAIT audit logger, and runtime posture evaluator.

### Service Registration & Orchestration Layer
- `scripts/register-mcps-with-defenseclaw.py` *(Modify)* — Adds `--select` parameter for selective server registration, `verify_model_guard_proxy(port=4000)` preflight connectivity probe, and fail-closed registration gate under `N2N_RISK_MODE=production`.
- `scripts/in2n-services.py` *(Modify)* — Adds `_mcp_unit_text()` generator helper for selective MCP user systemd units with kernel confinement directives (`NoNewPrivileges=yes`, `ProtectSystem=strict`, `PrivateTmp=yes`, `InaccessiblePaths=-%h/.openclaw/.env`), updates `cmd_generate()` for selective lists and sliced `.env.<mcp_name>` paths.
- `scripts/lib/mcp_compose.py` *(New File)* — Compose stack generator emitting hardened `docker-compose.mcp.yml` with container security opts (`no-new-privileges:true`, `read_only: true`, `cap_drop: ["ALL"]`, `tmpfs: ["/tmp"]`, sliced env mounts, network bridge to `:4000`).

### Installation Integration & Configuration Layer
- `scripts/install.sh` *(Modify)* — Adds optional selective MCP installer step invoking `scripts/mcp-installer.py`.
- `scripts/setup.sh` *(Modify)* — Adds optional selective MCP installer step invoking `scripts/mcp-installer.py`.
- `config/openclaw.json` / `~/.openclaw/config/openclaw.json` *(Managed Config Schema)* — Dynamic updates to `mcpServers` object matching selected/enabled servers (Single Source of Truth).

### Automated Test Suite Layer
- `tests/n2n/test_mcp_installer.py` *(New File)* — Unit & integration tests for installer CLI selection, secret slicing, and registration.
- `tests/n2n/test_mcp_posture_dual_target.py` *(New File)* — Posture calculation tests across systemd and docker-compose targets.
- `tests/n2n/test_model_guard_failclosed.py` *(New File)* — Tests verifying fail-closed pre-activation behavior when proxy is down or scan fails.
- `tests/target_parity.py` / `tests/n2n/test_target_parity.py` *(New File)* — Security directive parity tests between docker-compose OCI profile and systemd unit directives.
- `tests/fixtures/mcp_installer/` *(New Test Fixtures)* — Mock MCP server packages, mock master env, and HTTP proxy stub fixture (`mock_defenseclaw_proxy.py`).

---

## Surfaces / features touched
- **MCP Server Repository**: `mcp-servers/` (27+ server directories) & OpenClaw registration (`config/openclaw.json`).
- **Installer CLI/TUI Utility**: `scripts/mcp-installer.py`.
- **Pre-Activation Security & Model-Guard Proxy**: `scripts/scan-all-mcp-source.py` & DefenseClaw Go Proxy (`:4000`).
- **Dual Runtime Target Generators**: Host `systemd` user units via `in2n-services.py` & `docker-compose.mcp.yml` via `lib/mcp_compose.py`.
- **Environment Secret Isolation**: Sliced `.env.<mcp_name>` configs in `config/env/` with `0600` permissions.
- **Audit System**: GAIT append-only git trail in `~/.openclaw/n2n/gait/`.
- **Posture Engine**: Dynamic posture calculator reporting `production - enforced` vs `production - DEGRADED`.

---

## Variant relevance
- **Dual Runtime Target Variants**: `--target systemd` (native Linux kernel confinement) vs `--target docker-compose` (hardened container profile). Security directives across both targets must maintain strict functional parity and adhere to `openclaw.json` as single-source-of-truth.
- **Operational Posture Modes**: `production - enforced`, `production - DEGRADED (<reasons>)`, and `testing`.
- **Selective Server Combinations**: Arbitrary user-selected subsets of 27+ MCP servers.

---

## Test-invariants at risk
- [x] **Cross-path consistency**: Confinement parity between systemd host units (`NoNewPrivileges=yes`, `ProtectSystem=strict`, `PrivateTmp=yes`, `InaccessiblePaths=-%h/.openclaw/.env`) and Docker Compose container security options (`no-new-privileges:true`, `read_only: true`, `cap_drop: ["ALL"]`, `tmpfs: ["/tmp"]`, isolated env file mount). Both targets must align with `config/openclaw.json`.
- [x] **Variant isolation / Secret Isolation**: Sliced environment files (`.env.<mcp_name>`) must contain only required keys with `0600` permissions. Master `~/.openclaw/.env` must remain strictly inaccessible to worker processes and container mounts.
- [x] **Fail-closed pre-activation gate**: In `N2N_RISK_MODE=production`, an unreachable/offline Model-Guard proxy (:4000) or high/critical static scan findings MUST fail closed and prevent server enrollment/activation.
- [x] **Round-trip integrity / Single Source of Truth**: `config/openclaw.json` must serve as the authoritative single source of truth for registered MCP servers. All mutations must write append-only GAIT git audit entries to `~/.openclaw/n2n/gait/`.

---

## Stated intent / acceptance
- Operator can select/enable/bypass specific MCP servers via CLI or TUI wizard.
- Dual targets (`systemd` and `docker-compose`) provisioned cleanly according to `--target`.
- Under `N2N_RISK_MODE=production`, fail-closed pre-activation scanning and Model-Guard proxy socket check (:4000) enforced.
- Per-integration secret slicing (`0600` permissions) eliminates master `.env` exposure.
- Append-only GAIT git audit log records every installation/enrollment event.
- Posture calculation engine accurately reports `production - enforced` vs `production - DEGRADED`.

---

## Open questions

### Blocking (cannot plan tests):
*None.*

### Non-blocking (proceeding on assumption):
- **WSL2 Systemd Kernel Confinement**: Systemd security directives may be unsupported under WSL2 init. → *Assumption*: Posture engine detects WSL2 kernel limitations and degrades posture status to `production - DEGRADED (WSL2_kernel_limitation)` gracefully.
- **Non-Interactive Execution**: Installer executed in environment without TTY (e.g. CI/CD). → *Assumption*: `scripts/mcp-installer.py` auto-detects TTY and requires `--select` or `--all`, failing with exit code 1 if missing.
- **Proxy Socket Timeout**: Socket connection probe to proxy on port `:4000`. → *Assumption*: Socket probe implements a 3-second timeout before declaring proxy unreachable and triggering fail-closed abort.

---

## Verdict
**READY**
