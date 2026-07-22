# Solution Architecture Findings: MCP Server Installer with DefenseClaw Production Mode

**Intake ID**: `2026-07-21-mcp-installer-defenseclaw`  
**Feature**: Feature 057 — N2N Production Posture & Selective MCP Server Installer  
**Workspace**: `C:\Users\tyson\Documents\antigravity\amazing-babbage\netclaw`  
**Author**: Solution Architect (`intake-architect`)  
**Date**: 2026-07-21  

---

## 1. Executive Summary

This document presents the technical architecture and system design for the **Selective MCP Server Installer with DefenseClaw Production Mode** (`N2N_RISK_MODE=production`). The design addresses the requirement for selective activation of NetClaw's 27+ MCP servers while guaranteeing DefenseClaw security controls, fail-closed pre-activation scanning, secret isolation, GAIT auditing, and dual runtime provisioning (Docker Compose and host Systemd).

---

## 2. Affected Subsystems & Boundaries

```
                                  ┌──────────────────────────────────────────┐
                                  │      mcp-installer.py CLI / TUI          │
                                  └────────────────────┬─────────────────────┘
                                                       │
                                 ┌─────────────────────┴─────────────────────┐
                                 │       Pre-Activation Security Gate        │
                                 │ (scan-all-mcp-source.py / DefenseClaw)    │
                                 └─────────────────────┬─────────────────────┘
                                                       │
                   ┌───────────────────────────────────┴───────────────────────────────────┐
                   │                                                                       │
     ▼                                       ▼                                       ▼
┌─────────────────────────┐             ┌─────────────────────────┐             ┌─────────────────────────┐
│ Systemd Runtime Engine  │             │ Docker Compose Target   │             │ DefenseClaw & GAIT      │
│ (in2n-services.py)      │             │ (docker-compose.mcp.yml)│             │ (Proxy :4000 & Audit)   │
└─────────────────────────┘             └─────────────────────────┘             └─────────────────────────┘
```

1. **Selective MCP Installer Utility (`scripts/mcp-installer.py`)**:
   - CLI/TUI front-end enabling operator inspection, search, and toggle selection across `mcp-servers/`.
   - Modifies registration entries in `config/openclaw.json` / `~/.openclaw/config/openclaw.json`.
2. **Dual-Runtime Provisioning Engine**:
   - **Systemd Generator**: Integrates with `scripts/in2n-services.py` to produce hardened systemd user unit files.
   - **Docker Compose Generator**: Dynamically emits container specification files (`docker-compose.mcp.yml`) with production security constraints.
3. **DefenseClaw Pre-Activation Enforcer**:
   - Invokes `scripts/scan-all-mcp-source.py` prior to activation; enforces zero CRITICAL/HIGH security findings.
   - Interrogates Model-Guard proxy (`:4000`) for availability before enabling traffic routing.
   - Registers servers via `scripts/register-mcps-with-defenseclaw.py` (`defenseclaw mcp set`).
4. **Secret Isolation & Slicing Engine**:
   - Extracts required environment keys per MCP server to generate dedicated `.env.<mcp_name>` files.
   - Ensures no individual MCP server has access to the master `~/.openclaw/.env`.
5. **GAIT Audit & Posture Engine**:
   - Records installer operations (install, enable, disable, quarantine) in `~/.openclaw/n2n/gait/`.
   - Dynamic posture calculator evaluating runtime controls (`production - enforced` vs `production - DEGRADED`).

---

## 3. Current Workspace Design & Existing Components

Inspection of the `netclaw` codebase reveals strong foundational components that the installer will orchestrate:

- **`scripts/register-mcps-with-defenseclaw.py`**: Reads `openclaw.json` and executes `defenseclaw mcp set` for registered servers. Currently functions in bulk mode without selective filtering or dynamic target generation.
- **`scripts/in2n-services.py`**: Generates `systemd --user` unit files with kernel confinement parameters (`NoNewPrivileges=yes`, `ProtectSystem=strict`, `PrivateTmp=yes`, `InaccessiblePaths=-%h/.openclaw/.env`).
- **`scripts/scan-all-mcp-source.py`**: Static analysis engine scanning Python source files against 12 security patterns (`CG-CRED`, `CG-EXEC`, `CG-SQL`, `CG-DESER`, `CG-CRYPTO`, `CG-PATH`, `CG-TLS`).
- **`config/openclaw.json`**: Primary repository configuration mapping server commands, parameters, and environment overrides.
- **`scripts/defenseclaw-enable.sh`**: Existing shell initialization script for standalone DefenseClaw/OpenShell setup.

---

## 4. Architectural Evaluation & Trade-Offs (DEC-001 Dual Target)

### DEC-001: Dual Runtime Target Support (Systemd vs Docker Compose)

Per decision **DEC-001**, the installer must support both Linux host-native Systemd sandboxing and Docker Compose containerization.

| Dimension | Option A: Systemd Target (`--target systemd`) | Option B: Docker Compose Target (`--target docker-compose`) |
| :--- | :--- | :--- |
| **Sandbox Technology** | Host Linux Kernel cgroups/namespaces via systemd directives. | OCI Container namespaces, cgroups, and capabilities via Docker Engine. |
| **Confinement Security** | High (`NoNewPrivileges=yes`, `ProtectSystem=strict`, `InaccessiblePaths=-%h/.openclaw/.env`). | High (`security_opt: [no-new-privileges:true]`, `read_only: true`, `cap_drop: [ALL]`, `tmpfs: [/tmp]`). |
| **Portability** | Requires systemd host (Linux native). Degrades on WSL2/macOS. | Cross-platform (Linux, macOS, Windows with Docker Desktop/Engine). |
| **Secret Isolation** | File-system masking (`InaccessiblePaths`). | Dedicated env file mounting (`env_file: .env.<mcp>`); no host `.env` mounted. |
| **Network Routing** | Direct localhost loopback through `:4000` DefenseClaw proxy. | Docker bridge network routing container traffic through `defenseclaw-proxy:4000`. |
| **Posture Rating** | `production - enforced` (on native Linux). | `production - enforced` (container profile) or `production - DEGRADED (container_containment_only)`. |

### Trade-Off Decision
The installer will implement a unified target abstraction. `--target systemd` delegates service management to `in2n-services.py`. `--target docker-compose` dynamically builds a production `docker-compose.mcp.yml` containing isolated service blocks for each selected MCP server, interconnected via an isolated internal network bridge to the DefenseClaw proxy container.

---

## 5. Architectural Risks & Fail-Closed Security Controls

1. **Risk: Malicious or Compromised MCP Execution**  
   *Control*: Mandatory pre-activation static scan via `scan-all-mcp-source.py`. If any CRITICAL or HIGH severity finding is discovered, installation of that specific MCP server is immediately blocked.
2. **Risk: DefenseClaw Model-Guard Proxy Bypass**  
   *Control*: Fail-closed network configuration. In `N2N_RISK_MODE=production`, all MCP traffic must pass through port `:4000`. If port `:4000` is unresponsive or unconfigured, the installer refuses to activate services.
3. **Risk: Secret Escalation / Master `.env` Exposure**  
   *Control*: Automated environment slicing. Master credentials remain in `~/.openclaw/.env`. The installer parses only required keys for selected MCPs and outputs sliced `.env.<mcp_name>` files. Systemd units apply `InaccessiblePaths=-%h/.openclaw/.env`, and Docker Compose stacks only bind individual sliced env files.
4. **Risk: Dishonest Posture Reporting**  
   *Control*: Dynamic posture verification. The runtime posture engine interrogates active runtime controls (containment, proxy connectivity, audit logging, secret slicing). Missing host kernel confinement under container deployments is accurately reported as `production - DEGRADED` unless container containment meets full production criteria.

---

## 6. Recommended Implementation Approach

1. **Unified CLI Utility (`scripts/mcp-installer.py`)**:
   - Interactive selection via terminal menu when executed without flags.
   - Non-interactive flags: `--select <mcp1,mcp2>`, `--all`, `--target <systemd|docker-compose>`, `--dry-run`, `--risk-mode <production|testing>`.
2. **Sequential Pre-Activation Pipeline**:
   - **Step 1 (Discovery)**: Parse `mcp-servers/` directories and read existing `config/openclaw.json`.
   - **Step 2 (Selection & Filtering)**: Resolve target list of MCP servers based on user selection.
   - **Step 3 (Static Audit Gate)**: Run `scan-all-mcp-source.py` against selected server paths. Halt on CRITICAL/HIGH issues.
   - **Step 4 (Secret Isolation)**: Generate sliced `.env.<mcp_name>` files under `config/env/`.
   - **Step 5 (Target Provisioning)**:
     - For `systemd`: Invoke `in2n-services.py` to write units and update `managed_by=service`.
     - For `docker-compose`: Emit dynamic `docker-compose.mcp.yml` with hardened security opts and isolated network bridge.
   - **Step 6 (DefenseClaw Registration)**: Call `scripts/register-mcps-with-defenseclaw.py` to execute `defenseclaw mcp set`.
   - **Step 7 (Audit & Posture Log)**: Commit event to GAIT log (`~/.openclaw/n2n/gait/`) and recalculate posture state.

---
