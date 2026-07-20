# Implementation Plan: Knowledge Capability Cards & Knowledge-Aware Routing

**Branch**: `064-knowledge-capability-cards` | **Date**: 2026-07-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/064-knowledge-capability-cards/spec.md`

## Summary

Advertise each claw's local RAG collections (feature 062) as content-free, A2A-style
knowledge skills on the NCFED capability card, and route knowledge queries to the peer whose
corpus is authoritative — generalizing the demonstrated Hermes↔NetClaw book-summary interop
into deliberate, discoverable routing. The card gains one entry per RAG collection (from the
`rag_list` registry: title/topics/doc_type/counts, no content); retrieval is a dedicated
invocable knowledge-retrieval skill addressable from the card and fulfilled by the owner's
local agent/RAG (`rag_search`); the agent/router selects the corpus by semantic match on the
advertised description with a stable tiebreak. Reuses existing per-peer visibility, admission
tiers, default-deny authorization, and audit/GAIT (057/060). No new MCP server.

## Technical Context

**Language/Version**: Python 3.10+ (daemon + `bgp/federation/*`, matching 052–063); Markdown (SOUL/skill docs + NCFED draft §11 for -01)
**Primary Dependencies**: Existing only — `bgp/federation/inventory.py` (card), `router.py` (selection), `invocation.py`/`gateway.py` (retrieval turn), the feature-062 rag-mcp (`rag_list`, `rag_search`). No new third-party packages.
**Storage**: Reuses `~/.openclaw/rag/rag.db` (documents registry, read-only for advertisement) and the issued capability card. Per-peer visibility reuses existing federation.db rows. No new store.
**Testing**: pytest under `tests/n2n/` (card contents, no-secrets invariant, visibility filtering, deterministic selection, tier/authorization/audit on retrieval).
**Target Platform**: Linux (systemd --user mesh/member services), consistent with the live deployment.
**Project Type**: Extension of the existing NCFED daemon + capability card + RAG integration (single-project, in-repo).
**Performance Goals**: Advertisement derived from `rag_list` cheaply and refreshed with the card version (not per query); card growth bounded by metadata only, independent of corpus size (SC-005).
**Constraints**: Content-free card (no chunks/embeddings/source paths; passes `_assert_no_secrets`); retrieval possession-tier only + default-deny + audited; answers carry provenance.
**Scale/Scope**: Small mesh of mutually-known operators (NCFED applicability); tens of collections per claw at most.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| IV. Immutable Audit Trail | PASS — every federated retrieval audited with peer/corpus/GAIT (FR-007), reusing the existing trail. |
| V. MCP-Native Integration | PASS — advertisement reads rag-mcp `rag_list`; retrieval uses `rag_search` via the agent turn; no bespoke data path. |
| VI. Multi-Vendor / Agent Neutrality | PASS — knowledge advertised as an A2A-standard skill on the wire card; any implementation (Hermes, etc.) can consume it without shared code. |
| VII. Skill Modularity | PASS — knowledge exposed as a discrete, self-describing skill entry; no coupling to the requester's internals. |
| IX. Security by Default | PASS — content-free card, per-peer visibility, possession-tier + default-deny retrieval; sovereignty preserved (knowledge stays home). |
| XV. Backwards Compatibility | PASS — additive card field; a peer that ignores `knowledge` is unaffected; chat retrieval path retained. |
| XVI. Spec-Driven Development | PASS — this plan follows the spec; FR-010 keeps the NCFED draft §11 in sync. |
| XI. Full-Stack Artifact Coherence | PASS — plan lists every touchpoint (card, router, SOUL/skill docs, NCFED draft, tests); no orphan surface. |

No violations. Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/064-knowledge-capability-cards/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (card knowledge-skill + retrieval skill)
└── tasks.md             # Phase 2 (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
mcp-servers/protocol-mcp/bgp/federation/
├── inventory.py         # + build knowledge skills from rag_list; per-peer visibility; _assert_no_secrets covers them
├── router.py            # + knowledge-aware selection: semantic match on advertised descriptions, stable tiebreak
├── invocation.py        # + invocable knowledge-retrieval skill handler (default-deny, possession-tier, audited)
└── gateway.py           # retrieval turn reuses rag_search (wiring only)

workspace/skills/n2n-federation/SKILL.md   # + delegation guidance: prefer authoritative peer corpus; fallback peer→local→model; never fabricate a source
docs/ietf/draft-capobianco-ncfed-00.md     # §11 note staged for -01 (FR-010) — NOT the live -00 submission

tests/n2n/
├── test_knowledge_cards.py        # advertisement contents, no-secrets, visibility filtering, collection granularity
└── test_knowledge_routing.py      # deterministic semantic selection, fallback order, tier/authorization/audit on retrieval
```

**Structure Decision**: Single-project, in-repo extension of the existing federation package
and RAG integration. No new package or service; the four `bgp/federation/*` files above are
the code surface, plus the skill/SOUL doc and the (deferred) NCFED §11 update.

## Complexity Tracking

No constitution violations — section intentionally empty.
