# Implementation Tasks: Full NetClaw Voice Integration

**Feature**: 043-full-voice-integration
**Generated**: 2026-06-26
**Total Tasks**: 52

## Task Summary

| Phase | Description | Tasks |
|-------|-------------|-------|
| 1 | Setup | 4 |
| 2 | Foundational | 6 |
| 3 | US1 - Device Health (P1) | 4 |
| 4 | US2 - Lab Management (P1) | 4 |
| 5 | US3 - Config Analysis (P1) | 4 |
| 6 | US4 - Incidents (P2) | 4 |
| 7 | US5 - RFC Lookup (P2) | 4 |
| 8 | US6 - Memory Queries (P2) | 4 |
| 9 | US7 - Proactive Alerts (P2) | 5 |
| 10 | US8 - Multi-Turn Context (P2) | 4 |
| 11 | US9 - Topology (P3) | 3 |
| 12 | US10 - Twitter Voice (P3) | 3 |
| 13 | Polish & Documentation | 3 |

---

## Phase 1: Setup

**Goal**: Initialize project structure and configuration files

- [ ] T001 Create voice config directory at ~/.openclaw/voice/
- [ ] T002 Create caller whitelist template at ~/.openclaw/voice/whitelist.json
- [ ] T003 Create alert triggers template at ~/.openclaw/voice/alert_triggers.json
- [ ] T004 Add voice environment variables to ~/.openclaw/.env.example

---

## Phase 2: Foundational

**Goal**: Core infrastructure needed by all user stories

- [ ] T005 Implement SpeechFormatter class in mcp-servers/twilio-voice-mcp/speech_formatter.py
- [ ] T006 [P] Implement IP address formatting (10.0.0.1 → "10 dot 0 dot 0 dot 1") in mcp-servers/twilio-voice-mcp/speech_formatter.py
- [ ] T007 [P] Implement number/percentage formatting in mcp-servers/twilio-voice-mcp/speech_formatter.py
- [ ] T008 [P] Implement list truncation (>5 items → summary) in mcp-servers/twilio-voice-mcp/speech_formatter.py
- [ ] T009 Implement ConversationContext dataclass in mcp-servers/twilio-voice-mcp/context_manager.py
- [ ] T010 Implement ContextManager with Memory MCP persistence in mcp-servers/twilio-voice-mcp/context_manager.py

---

## Phase 3: US1 - Voice-Activated Network Device Health Check (P1)

**Story Goal**: User calls NetClaw and says "Check the health of router R1" → receives spoken health report

**Independent Test**: Call NetClaw, say "Check the health of my network devices", verify spoken response with CPU/memory/interface status

- [ ] T011 [US1] Create voice-network-health skill directory at workspace/skills/voice-network-health/
- [ ] T012 [US1] Write SKILL.md for voice-network-health at workspace/skills/voice-network-health/SKILL.md
- [ ] T013 [US1] Implement device health voice handler in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T014 [US1] Add pyATS health response formatting to mcp-servers/twilio-voice-mcp/speech_formatter.py

---

## Phase 4: US2 - Voice-Controlled Lab Management (P1)

**Story Goal**: User says "Start the BGP lab" → lab starts, progress updates spoken

**Independent Test**: Call NetClaw, say "What labs do I have?", then "Start [lab name]", verify lab starts

- [ ] T015 [US2] Create voice-lab-management skill directory at workspace/skills/voice-lab-management/
- [ ] T016 [US2] Write SKILL.md for voice-lab-management at workspace/skills/voice-lab-management/SKILL.md
- [ ] T017 [US2] Implement CML/GNS3 voice handlers in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T018 [US2] Add lab status response formatting to mcp-servers/twilio-voice-mcp/speech_formatter.py

---

## Phase 5: US3 - Voice-Driven Configuration Analysis (P1)

**Story Goal**: User says "Show me BGP neighbors on R1" → spoken neighbor table

**Independent Test**: Call NetClaw, ask about BGP/OSPF/interfaces, verify accurate spoken config data

- [ ] T019 [US3] Implement BGP neighbor voice query in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T020 [US3] Implement OSPF adjacency voice query in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T021 [US3] Implement interface status voice query in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T022 [US3] Add routing protocol response formatting to mcp-servers/twilio-voice-mcp/speech_formatter.py

---

## Phase 6: US4 - Incident Management via Voice (P2)

**Story Goal**: User says "Any active incidents?" → spoken incident list, can acknowledge

**Independent Test**: Call NetClaw, ask about incidents, acknowledge one, verify PagerDuty updated

- [ ] T023 [US4] Create voice-incident-management skill directory at workspace/skills/voice-incident-management/
- [ ] T024 [US4] Write SKILL.md for voice-incident-management at workspace/skills/voice-incident-management/SKILL.md
- [ ] T025 [US4] Implement PagerDuty voice handlers in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T026 [US4] Add incident response formatting to mcp-servers/twilio-voice-mcp/speech_formatter.py

---

## Phase 7: US5 - RFC and Documentation Lookup (P2)

**Story Goal**: User says "Look up RFC 2328" → spoken RFC summary

**Independent Test**: Call NetClaw, ask for RFC lookup, verify spoken summary

- [ ] T027 [US5] Create voice-rfc-lookup skill directory at workspace/skills/voice-rfc-lookup/
- [ ] T028 [US5] Write SKILL.md for voice-rfc-lookup at workspace/skills/voice-rfc-lookup/SKILL.md
- [ ] T029 [US5] Implement RFC voice handlers in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T030 [US5] Add RFC response formatting (long text → digestible chunks) to mcp-servers/twilio-voice-mcp/speech_formatter.py

---

## Phase 8: US6 - Memory and Context Queries (P2)

**Story Goal**: User says "What do you remember about the migration?" → spoken facts

**Independent Test**: Store a fact, call back later, ask about it, verify recall

- [ ] T031 [US6] Create voice-memory-query skill directory at workspace/skills/voice-memory-query/
- [ ] T032 [US6] Write SKILL.md for voice-memory-query at workspace/skills/voice-memory-query/SKILL.md
- [ ] T033 [US6] Implement Memory MCP voice handlers in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T034 [US6] Add memory response formatting to mcp-servers/twilio-voice-mcp/speech_formatter.py

---

## Phase 9: US7 - Proactive Outbound Alerts (P2)

**Story Goal**: Critical event triggers → NetClaw calls engineer with details

**Independent Test**: Configure trigger, simulate event, verify outbound call received

- [ ] T035 [US7] Implement AlertTrigger dataclass in mcp-servers/twilio-voice-mcp/alert_triggers.py
- [ ] T036 [US7] Implement AlertTriggerManager with config file loading in mcp-servers/twilio-voice-mcp/alert_triggers.py
- [ ] T037 [US7] Implement outbound call initiation in mcp-servers/twilio-voice-mcp/alert_triggers.py
- [ ] T038 [US7] Integrate alert triggers with PagerDuty MCP events in mcp-servers/twilio-voice-mcp/alert_triggers.py
- [ ] T039 [US7] Integrate alert triggers with pyATS health check events in mcp-servers/twilio-voice-mcp/alert_triggers.py

---

## Phase 10: US8 - Multi-Turn Conversation with Context (P2)

**Story Goal**: User says "Check R1" then "What's its uptime?" → context maintained

**Independent Test**: Call, reference device, follow up with "it/its", verify correct resolution

- [ ] T040 [US8] Implement entity extraction (device/lab/interface names) in mcp-servers/twilio-voice-mcp/context_manager.py
- [ ] T041 [US8] Implement pronoun resolution ("it", "its", "that") in mcp-servers/twilio-voice-mcp/context_manager.py
- [ ] T042 [US8] Implement conversation summary generation in mcp-servers/twilio-voice-mcp/context_manager.py
- [ ] T043 [US8] Add context persistence to Memory MCP per caller ID in mcp-servers/twilio-voice-mcp/context_manager.py

---

## Phase 11: US9 - Network Topology Description (P3)

**Story Goal**: User says "Describe my network topology" → verbal description

**Independent Test**: Call, ask about topology, verify accurate verbal description

- [ ] T044 [US9] Implement topology verbal description in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T045 [US9] Implement path description ("How does traffic flow from A to B?") in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T046 [US9] Add topology response formatting to mcp-servers/twilio-voice-mcp/speech_formatter.py

---

## Phase 12: US10 - Twitter Integration via Voice (P3)

**Story Goal**: User says "Post a tweet about the upgrade" → tweet posted

**Independent Test**: Call, dictate tweet, verify posted to Twitter

- [ ] T047 [US10] Implement Twitter post voice handler in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T048 [US10] Implement Twitter mentions voice query in mcp-servers/twilio-voice-mcp/voice_tools.py
- [ ] T049 [US10] Add Twitter response formatting to mcp-servers/twilio-voice-mcp/speech_formatter.py

---

## Phase 13: Polish & Documentation

**Goal**: Finalize documentation and cross-cutting concerns

- [ ] T050 Update README.md with voice integration documentation
- [ ] T051 Update SOUL.md with voice capabilities
- [ ] T052 Add voice configuration to install.sh setup wizard

---

## Dependencies

```
Phase 1 (Setup) → Phase 2 (Foundational)
Phase 2 → Phase 3, 4, 5 (P1 stories can run in parallel)
Phase 3, 4, 5 → Phase 6, 7, 8, 9, 10 (P2 stories can run in parallel)
Phase 6-10 → Phase 11, 12 (P3 stories)
Phase 11, 12 → Phase 13 (Polish)
```

## Parallel Execution Opportunities

**Within Phase 2** (Foundational):
- T006, T007, T008 can run in parallel (independent formatters)

**P1 Stories** (Phases 3, 4, 5):
- All three P1 user stories can be implemented in parallel after Phase 2

**P2 Stories** (Phases 6, 7, 8, 9, 10):
- Phases 6, 7, 8 can run in parallel (independent MCP integrations)
- Phase 9 (Alerts) depends on Phase 6 (PagerDuty handlers)
- Phase 10 (Context) should complete before P3 stories for full context support

**P3 Stories** (Phases 11, 12):
- Can run in parallel after P2 completion

## Implementation Strategy

**MVP (Minimum Viable Product)**: Phase 1-3 only
- Setup + Foundational + Device Health
- Provides core voice → pyATS integration
- ~14 tasks, independently testable

**Iteration 2**: Add P1 stories (Phases 4-5)
- Lab management + Config analysis
- Completes high-frequency use cases

**Iteration 3**: Add P2 stories (Phases 6-10)
- Incidents, RFC, Memory, Alerts, Context
- Full feature set minus nice-to-haves

**Iteration 4**: Add P3 stories + Polish (Phases 11-13)
- Topology, Twitter, Documentation
- Complete feature
