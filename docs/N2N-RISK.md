# A Risk of NetClaws — Internal Federation (iN2N)

> A **risk** is the (real) collective noun for a group of lobsters. NetClaw is a
> lobster. So a coordinated group of NetClaws is **a risk of NetClaws** — and,
> for a security-adjacent product, the pun is intentional.

iN2N (internal NetClaw-to-NetClaw federation) lets **one operator** run a group
of **focused, specialized NetClaws** — a *risk* — coordinated by a single
**Border Claw**. You only ever talk to the Border; it routes each request to the
member claw that owns the capability and returns the result. It is the internal
counterpart to **eN2N** (external federation between *different* operators over
the NCFED mesh — see [N2N-PEERING-NETCLAWS.md](../N2N-PEERING-NETCLAWS.md)).

## Why

One monolithic NetClaw carrying 190+ skills is expensive (huge context per turn)
and blast-radius-wide (every credential in one process). A risk splits that into
small specialists:

- **Focus & token economy** — a CML claw carries ~5 skills, not 190; a pyATS
  claw carries only pyATS. Each member's context stays small and cheap.
- **Least privilege** — each member gets *only* its integration's secrets. A
  compromised CML claw literally has no path to your Azure or firewall creds.
- **One door, one audit trail** — the Border is the single interface, the single
  external identity, and the single place every action is logged.

## The model

```
                    (you talk only to the Border)
                              │
                    ┌─────────▼─────────┐        eN2N (NCFED mesh)
   external ◄───────┤    BORDER CLAW    ├───────► other operators' risks
   peer risks       │  gateway · comms  │         (Border-to-Border only)
                    │  routing · audit  │
                    └───┬───┬───┬───┬───┘
                iN2N (internal transport — members dial OUT)
                    │   │   │   │
                  ┌─▼┐┌─▼┐┌─▼┐┌─▼┐   ... each a focused, scoped member claw
                  │cml││pyats││azure││ise│   (CML claw, pyATS claw, Azure claw, …)
                  └──┘└────┘└─────┘└───┘
```

- **Standalone** — a classic NetClaw is simply "a risk of one, its own Border".
- **Border Claw** — the only claw with the gateway and comms (Slack/Discord/
  Webex/Twilio/Twitter/PagerDuty/ServiceNow), routing, audit/GAIT, memory, and
  humanrail. Deliberately carries **no** domain skills — its job is to broker.
  Exactly one per risk. It also runs eN2N (external federation) if enabled.
- **Member Claw** — a tightly-scoped specialist (one vendor/tool per claw). Dials
  the Border, runs delegated tasks over only its scoped MCPs, never talks to the
  outside world. Base floor on every member: iN2N runtime + self-status + memory
  + GAIT + humanrail escalation.

## Key properties

- **Hub-and-spoke, no mesh.** Members **dial outbound** to the Border's one
  reachable endpoint — loopback when co-located, or a private-network / overlay-
  VPN / tunnel address when distributed across hosts/clouds/datacenters. No
  inbound ports on members, no ngrok, **no iBGP/mesh** — the Border is the hub.
- **Trust = pinned key, not consent.** A member enrolls once with a single-use
  token and its own runtime-generated self-signed key, which the Border pins
  (trust-on-first-use). No CA. eN2N's mutual-consent model applies only *between*
  risks, at the Border boundary.
- **One external identity.** To a peer risk, the whole risk appears as one
  identity (the Border). Member identities/endpoints/topology never leak. The
  Border advertises the **aggregate** of member capabilities under the risk (so a
  peer learns "this risk can do CML, pyATS, Azure…") without exposing structure.
- **Any provider/model per claw.** Each member is its own OpenClaw *embedded*
  agent (`openclaw agent --local --model <provider/model>`) — Anthropic, OpenAI,
  Google, or **local/Ollama**, mixed freely. The Border can reason on a flagship
  model while members run cheaper/faster ones.
- **Hybrid runtime (cold/on-demand).** A hot set stays always-on; other members
  idle-exit when quiet and the Border **cold-starts** them on the next route
  (spawns, waits for enrollment, delegates). Big resource/token savings.
- **Security posture is a risk mode.** `N2N_RISK_MODE=testing` (fast iteration,
  no guards) vs `production` (DefenseClaw + OpenShell sandbox enforced — members
  run sandboxed under [OpenShell](DEFENSECLAW.md)).
- **Enforced scope.** A member refuses out-of-scope work even from its Border.

## Roles at install

The installer asks: **standalone**, **Border**, or **Member**. A Border chooses
`eN2N` / `iN2N` / `both`. A Member points at its Border and enrolls. This is the
**primary** path — a fresh install stands up a risk directly; an existing
monolith can also be *migrated* into one (below).

## Profiles (env-gated, one claw per vendor/tool)

Member profiles are **derived from your installed skill catalog** and **gated on
their backend being configured** — you are never offered a member you can't run.

```bash
python3 scripts/in2n-profiles.py list          # members you can run right now
python3 scripts/in2n-profiles.py list --all     # + dormant (skills present, no backend)
python3 scripts/in2n-profiles.py show cml        # skills in the cml member
```

Granularity is per vendor/tool: `cml`, `containerlab`, `pyats`, `ipfabric`,
`suzieq`, `batfish`, `forward`, `gtrace`, `packet`, `itential`, `aap`, `nso`,
`aci`, `catalyst-center`, `f5`, `meraki`, `sdwan`, `ise`, `asa`, `checkpoint`,
`paloalto`, `fortimanager`, `zscaler`, `claroty`, `nmap`, `nvd`, `fwrule`, `aws`,
`azure`, `gcp`, `netbox`, `nautobot`, `infrahub`, `infoblox`, `github`. Utilities
like visualization (`viz`) stay grouped. DefenseClaw + OpenShell are the
production-mode security layer.

## Operating a risk

On the Border (MCP tools, or `netclaw risk …` / the `netclaw` TUI):

| Action | Tool / command |
|--------|----------------|
| Risk status (role, stacks, members) | `n2n_risk_status` · `netclaw risk status` |
| List members (scope, state, live) | `n2n_member_list` · `netclaw risk members` |
| Member health / quarantine alerts | `n2n_member_health` · `netclaw risk health` |
| Provision a member (+ token) | `n2n_member_add` · `netclaw risk add <profile> <name>` |
| Issue an enrollment token | `n2n_enroll_token` · `netclaw risk token` |
| Route a request to a member | `n2n_route` · `netclaw risk route "<request>"` |
| Remove a member (unpin) | `n2n_member_remove` · `netclaw risk remove <id>` |

Members run the lightweight launcher `scripts/in2n-member.py` (dial + enroll +
execute; `--idle-exit N` for cold/on-demand).

## Migrating a monolith into a risk

`scripts/in2n-migrate.py` is **generate-only** — it never stops/starts/removes
anything. It reads your existing `~/.openclaw/.env` and produces, in a
gitignored `migration-staging/`, a **least-privilege `.env` slice** + launcher
per member, a `border.env.additions`, and a step-by-step **`RUNBOOK.md`** for a
**parallel cutover** (backup → promote to Border alongside the running monolith →
bring up members one at a time → move comms to the Border last → decommission the
monolith last, with a rollback path).

```bash
python3 scripts/in2n-migrate.py --risk my-risk --border-endpoint 127.0.0.1:11790
# review migration-staging/RUNBOOK.md — then run it by hand
```

## Environment

See `.env.example` (`N2N_ROLE`, `N2N_RISK_NAME`, `N2N_ENABLED_STACKS`,
`N2N_IN2N_PORT`, `N2N_BORDER_ENDPOINT`, `N2N_QUARANTINE_THRESHOLD`, and the member
vars `N2N_MEMBER_ID` / `N2N_MEMBER_MODEL` / `N2N_MEMBER_SCOPE` /
`N2N_ENROLLMENT_TOKEN` / `N2N_IDLE_EXIT_S`).

## See also

- [N2N-PEERING-NETCLAWS.md](../N2N-PEERING-NETCLAWS.md) — eN2N (external peering)
- [N2N-RISK-MIGRATION-FOR-PEERS.md](N2N-RISK-MIGRATION-FOR-PEERS.md) — for peers
  (Nick/Byrn): what changed and whether you need to do anything
- [DEFENSECLAW.md](DEFENSECLAW.md) — the production-mode security layer
- Spec: `specs/056-in2n-internal-federation/`
