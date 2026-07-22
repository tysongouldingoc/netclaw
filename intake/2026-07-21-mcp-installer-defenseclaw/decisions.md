# Decision Log — mcp-installer-defenseclaw

> Every clarifying / blocking question the team raised on this request, the
> context behind it, the options offered, and the choice made. Readable on its
> own — someone should be able to open this months later and understand *what we
> decided and why*. Newest decisions at the bottom.
>
> Status values: **PENDING** (asked, awaiting answer) · **DECIDED** ·
> **PARKED** (deferred to stakeholder / later) · **SUPERSEDED** (a later
> decision overrode this one — link it).

---

## DEC-001 — Docker Compose vs Host Systemd Kernel Confinement Scope
- **Item / area:** Custom MCP Installer / Execution Runtime Architecture
- **Status:** DECIDED
- **Raised:** 2026-07-21 · **Decided:** 2026-07-21 · **Decided by:** User
- **Recurring-issue link:** —

### The question
How should the custom installer reconcile Docker Compose deployment with host-level systemd kernel confinement (`NoNewPrivileges`, `ProtectSystem=strict`) specified for member sandboxes?

### Where we're coming from (history, as of when)
The prompt asks for a custom selective MCP server installer that can be deployed via Docker Compose, while simultaneously specifying Feature 057 (DefenseClaw Production Mode) Control 1: Member sandbox using host-level kernel confinement via systemd units, specifically noting that OpenShell/containers were evaluated and rejected for live-infra members due to empty/egress-denied sandbox limitations.

### Options presented
- **A) Dual Runtime Target Support (Recommended)** — Support `--target docker-compose` (with hardened Docker container profiles, e.g. `security_opt: [no-new-privileges:true]`, read-only root filesystems, and volume mounts) alongside `--target systemd` for native Linux host systemd confinement. Posture reports `production - enforced` for host systemd and `production - DEGRADED` or container-enforced depending on control checks.
- **B) Docker Compose for DefenseClaw Services Only** — Use Docker Compose to orchestrate core infrastructure (DefenseClaw Go Proxy :4000, GAIT audit logger, SQLite) while member MCP servers run natively as user systemd units on the host machine.
- **C) Hardened Container-Native Sandbox** — Map member systemd security constraints directly to Docker Compose container security features (`cap_drop`, `security_opt`, `read_only`, `tmpfs`), treating hardened Docker containers as the production sandbox implementation under Compose.

### Decision
**Chosen:** Option A — Dual Runtime Target Support
**Note from decision-maker:** Support both `--target docker-compose` (using hardened Docker security options) and `--target systemd` (using host kernel systemd confinement).
**Rationale / implications:** The installer will support `--target docker-compose` producing a hardened `docker-compose.yml` for containerized environments, and `--target systemd` for native Linux host systemd kernel confinement. Honest posture reporting will evaluate controls per target.

---
