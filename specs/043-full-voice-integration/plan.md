# Implementation Plan: Full NetClaw Voice Integration

**Branch**: `043-full-voice-integration` | **Date**: 2026-06-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/043-full-voice-integration/spec.md`

## Summary

Expand the existing Twilio Voice MCP (Feature 042) to provide comprehensive voice access to ALL NetClaw capabilities. The system accepts inbound calls (and initiates outbound alerts), transcribes speech via Twilio/Whisper, processes commands through Claude with full MCP tool access, and responds with natural speech. Key additions include: pyATS device queries, CML/GNS3 lab management, PagerDuty incident handling, RFC lookups, Memory MCP integration, per-caller context persistence, and proactive outbound alerting.

## Technical Context

**Language/Version**: Python 3.10+ (webhook server, skills), Node.js 18+ (Twilio MCP)
**Primary Dependencies**: FastMCP, Twilio SDK, @twilio-alpha/mcp, Anthropic SDK, httpx, existing MCP servers (pyATS, CML, GNS3, PagerDuty, RFC, Memory, Twitter)
**Storage**: Memory MCP (conversation context per caller ID), SQLite (call audit logs)
**Testing**: pytest (webhook server), manual voice testing, integration tests via Twilio test credentials
**Target Platform**: Linux server (NetClaw host), Twilio cloud (voice infrastructure)
**Project Type**: MCP server extension + webhook service + skills
**Performance Goals**: <5s response latency for simple queries, <60s for complex MCP tool chains
**Constraints**: 30-minute max call duration, 10 concurrent sessions, 2-hour mention freshness window
**Scale/Scope**: Single user (John) initially, extensible to team via caller ID whitelist

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Safety-First Operations | PASS | Voice commands go through same MCP tools with existing safety guards |
| II. Read-Before-Write | PASS | All device operations use existing pyATS MCP which observes before modifying |
| III. ITSM-Gated Changes | PASS | Production changes still require CR approval via ServiceNow |
| IV. Immutable Audit Trail | PASS | All voice sessions logged to Memory MCP and call transcripts stored |
| V. MCP-Native Integration | PASS | Extends existing Twilio MCP, uses FastMCP framework |
| VI. Multi-Vendor Neutrality | PASS | Voice layer is vendor-agnostic; delegates to vendor-specific MCPs |
| VII. Skill Modularity | PASS | Voice handling is separate skill, composes with existing MCP tools |
| VIII. Verify After Every Change | PASS | Device changes verified via existing MCP verification patterns |
| IX. Security by Default | PASS | Caller ID whitelist, no credentials spoken aloud |
| X. Observability | PASS | Call logs, transcripts, metrics exposed via Memory MCP |
| XI. Full-Stack Artifact Coherence | PENDING | Must update README, SOUL.md, install.sh, .env.example at completion |
| XII. Documentation-as-Code | PENDING | SKILL.md required for voice skills |
| XIII. Credential Safety | PASS | Twilio creds in .env, never spoken |
| XIV. Human-in-the-Loop | PASS | Voice is human-initiated; outbound alerts are configured explicitly |
| XV. Backwards Compatibility | PASS | Extends Feature 042, doesn't break existing functionality |
| XVI. Spec-Driven Development | PASS | Following speckit workflow |
| XVII. Milestone Documentation | PENDING | Blog post required at completion |

**Gate Status**: PASS - No blocking violations. Pending items are completion-phase artifacts.

## Project Structure

### Documentation (this feature)

```text
specs/043-full-voice-integration/
├── spec.md              # Feature specification (complete)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (voice command schemas)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
mcp-servers/twilio-voice-mcp/
├── server.js            # Existing Twilio MCP server (Node.js)
├── webhook_server.py    # Existing voice webhook (Python) - EXTEND
├── voice_tools.py       # NEW: Voice-specific tool implementations
├── context_manager.py   # NEW: Per-caller conversation context
├── speech_formatter.py  # NEW: Response formatting for natural speech
└── alert_triggers.py    # NEW: Proactive outbound alert configuration

workspace/skills/
├── voice-network-health/SKILL.md     # NEW: Device health via voice
├── voice-lab-management/SKILL.md     # NEW: CML/GNS3 via voice
├── voice-incident-management/SKILL.md # NEW: PagerDuty via voice
├── voice-rfc-lookup/SKILL.md         # NEW: RFC queries via voice
└── voice-memory-query/SKILL.md       # NEW: Memory MCP via voice

tests/
├── voice/
│   ├── test_context_manager.py
│   ├── test_speech_formatter.py
│   └── test_alert_triggers.py
└── integration/
    └── test_voice_e2e.py
```

**Structure Decision**: Extend existing `mcp-servers/twilio-voice-mcp/` with new Python modules. Create voice-specific skills in `workspace/skills/`. This maintains separation between Twilio transport (Node.js MCP) and voice processing logic (Python webhook + skills).

## Complexity Tracking

No constitution violations requiring justification. Design follows existing patterns.
