# PM Plan — mcp-installer-defenseclaw

> Authored by `intake-project-manager`. **This is the document the user reads first.**
> It answers: what is this really, where is it coming from, and how do we stop security drift and operational friction from recurring.

---

## 1. Request Summary
The client requests a custom selective MCP server installer utility (`scripts/mcp-installer.py`) for NetClaw that allows operators to interactively or via CLI flags select which subset of NetClaw's 27+ MCP servers to install and enable. The installer must support deployment across two execution targets — containerized Docker Compose stacks (`--target docker-compose`) and native host Systemd user services (`--target systemd`) — while enforcing **DefenseClaw Production Mode** (`N2N_RISK_MODE=production`). The posture enforcement mandates fail-closed pre-activation static security scanning (`scripts/scan-all-mcp-source.py`), Model-Guard proxy routing (`:4000`), least-privilege sliced `.env.<mcp_name>` secret isolation, append-only GAIT audit logging (`~/.openclaw/n2n/gait/`), and dynamic posture state calculation (`production - enforced` vs `production - DEGRADED`).

---

## 2. Request Type
**`new-feature`**

### Classification Reasoning:
- **Not a bug**: Existing registration tools (`scripts/register-mcps-with-defenseclaw.py`) and service generators (`scripts/in2n-services.py`) function as designed for bulk setup.
- **Not a regression**: No existing functionality broke; the system currently lacks selective installer capabilities, dynamic Docker Compose target output generation, and automated pre-activation secret slicing.
- **`new-feature` (Feature 057)**: This ask introduces an architectural utility expanding operator control over NetClaw's deployment footprint while establishing an automated pre-activation security gate.

---

## 3. History / Background

### Sources Checked:
- **Persistent Memory**:
  - Global intake memory: `~/.gemini/config/plugins/delivery-team-plugin/skills/team-intake/memory/request-log.md` and `decision-log.md` (no prior NetClaw intakes recorded).
  - Project context: Searched workspace `netclaw` (no existing `PROJECT-CONTEXT.md` or defect-class catalog).
- **Librarian Index**:
  - Searched for active library `TABLE-OF-CONTENTS.md` (miss; no prior archived patterns for NetClaw MCP installer).
- **Codebase & Documentation Record**:
  - `docs/N2N-RISK.md` — Defines Feature 057 (N2N Production Posture & Selective MCP Installer).
  - `DefenseClawMCPScan.md` — Documents historical baseline audit (42 clean MCP server directories).
  - `scripts/register-mcps-with-defenseclaw.py` — Pre-existing bulk registration utility.
  - `scripts/in2n-services.py` — Pre-existing systemd user service generator with kernel confinement (`NoNewPrivileges`, `ProtectSystem=strict`, `InaccessiblePaths=-%h/.openclaw/.env`).

### Have we seen this before?
**No (0 prior touches on record)**. This is the initial intake for selective MCP installer orchestration and dual-runtime posture generation.

---

## 4. Recurrence Diagnosis & Prevention
While this is a new feature request, monolithic and manual MCP deployments historically introduce chronic security drift traps:
1. **Secret Exposure Drift**: Shared master `.env` files exposed directly to all worker processes.
2. **Unmonitored Traffic Escalation**: MCP servers bypassing Model-Guard inspection by binding direct un-proxied sockets.
3. **Unhardened Container Drift**: Container deployments running with default over-privileged Linux capabilities.

### Systemic Cycle Breaker:
To prevent future security drift and operational rework, the installer implements a **durable dual-runtime target generator paired with an un-bypassable pre-activation security gate**:
- **Dual-Runtime Generation (DEC-001)**: Native Systemd user units (`NoNewPrivileges=yes`, `ProtectSystem=strict`) and hardened Docker Compose stacks (`security_opt: [no-new-privileges:true]`, `read_only: true`, `cap_drop: [ALL]`, `tmpfs: [/tmp]`).
- **Fail-Closed Pre-Activation Gate**: Mandatory static scan via `scan-all-mcp-source.py` and Model-Guard proxy socket probe (`:4000`). If scanning yields HIGH/CRITICAL issues or proxy is offline in production mode, activation is strictly aborted.
- **Least-Privilege Secret Slicing**: Per-MCP `.env.<mcp_name>` creation with `0600` file permissions; master `.env` remains completely un-mounted.

---

## 5. Where This Is Coming From
The requirement originates from operational deployment demands: enterprise operators require lightweight, tailored NetClaw deployments (e.g. running only 2 or 3 network MCPs rather than all 27+) without compromising the 7 core security controls specified in **DefenseClaw Production Mode** (`N2N_RISK_MODE=production`).

---

## 6. Recommendation to the Human

### What to Approve:
Approve the technical design for `scripts/mcp-installer.py` featuring:
1. Interactive CLI selection wizard + non-interactive CLI flags (`--select`, `--all`, `--target`, `--mode`).
2. Secret slicing engine creating per-MCP isolated `.env` files.
3. Dual target generation (`docker-compose` stack vs `systemd` user services per DEC-001).
4. Automated fail-closed pre-activation security gate.
5. GAIT audit logging (`~/.openclaw/n2n/gait/`) and dynamic posture status calculation.

### Cost / Scope Framing:
- **Category**: New Feature Implementation (Feature 057).
- **Scope**: Clean & contained (~3 to 5 engineering days). Utilizes pre-existing static scanner (`scan-all-mcp-source.py`), systemd generator (`in2n-services.py`), and registration scripts.

### Durable Fix / Architectural Prevention:
Do not permit inline shortcuts or optional bypasses on pre-activation scanning. All selected MCP servers must undergo DefenseClaw scanning and receive isolated secret slices regardless of target runtime.

---

## 7. Open Decisions & Alignment Items

### Decided:
- **DEC-001: Dual-Runtime Target Support (DECIDED by User on 2026-07-21)**:
  - *Decision*: Support both `--target docker-compose` (hardened container profiles) and `--target systemd` (host Linux kernel confinement). Posture assessment dynamically checks control parity per target.

### Non-Blocking Recommendations:
- [x] **CI/CD TTY Auto-Detection**: Auto-detect TTY state in `mcp-installer.py`; fall back to CLI flag requirements in non-interactive batch execution.
- [x] **Un-configured Secret Handling**: Prompt for missing environment variables interactively or generate `.env.<mcp_name>.template` and flag status as `degraded-pending-secrets`.

---

*Memory updated:* `request-log.md` ✅ (appended entry for `2026-07-21-mcp-installer-defenseclaw`) · project defect catalog N/A (none configured).
