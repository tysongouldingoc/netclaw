# Feature Specification: Full NetClaw Voice Integration

**Feature Branch**: `043-full-voice-integration`
**Created**: 2026-06-26
**Status**: Draft
**Input**: User description: "Full NetClaw Voice Integration - Complete phone access to all NetClaw capabilities including pyATS, CML, Memory MCP, PagerDuty, RFC lookups, and more. Anything NetClaw can do via CLI should be accessible over the phone."

## Overview

This feature expands the existing Twilio Voice MCP (Feature 042) to provide comprehensive voice access to ALL NetClaw capabilities. Users can call NetClaw and perform any operation available through the CLI - from running pyATS tests to checking PagerDuty incidents, querying RFC documentation, managing CML labs, and receiving proactive alerts. The system maintains conversation context across multi-turn interactions and formats all responses for natural speech delivery.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Voice-Activated Network Device Health Check (Priority: P1)

A network engineer driving to work receives an alert about potential issues. They call NetClaw to get a quick health check of their network devices without needing to open a laptop.

**Why this priority**: Core value proposition - hands-free network operations during emergencies or when CLI access is impractical. Most frequently needed capability.

**Independent Test**: Can be fully tested by calling NetClaw and asking "Check the health of my network devices" - delivers immediate operational visibility.

**Acceptance Scenarios**:

1. **Given** the user is on a call with NetClaw, **When** they say "Check the health of router R1", **Then** NetClaw queries pyATS, retrieves device status (CPU, memory, interface states, uptime), and speaks a summarized health report.
2. **Given** multiple devices are configured, **When** the user says "Give me a network health summary", **Then** NetClaw aggregates health data across all devices and reports any anomalies first, followed by healthy systems.
3. **Given** a device is unreachable, **When** the user asks for its health, **Then** NetClaw reports the connectivity issue and suggests troubleshooting steps.

---

### User Story 2 - Voice-Controlled Lab Management (Priority: P1)

An engineer needs to start or stop CML/GNS3 labs while away from their workstation - perhaps preparing for a demo or shutting down resources to save costs.

**Why this priority**: Lab management is time-sensitive and frequently needed. Builds on existing Feature 042 CML integration.

**Independent Test**: Can be tested by calling and saying "Start my BGP lab" - lab actually starts and user receives confirmation.

**Acceptance Scenarios**:

1. **Given** CML labs exist, **When** the user says "What labs do I have?", **Then** NetClaw lists all labs with their current state (running/stopped), node counts, and names.
2. **Given** a stopped lab exists, **When** the user says "Start the OSPF training lab", **Then** NetClaw initiates lab startup and provides progress updates ("Lab is starting... 3 of 5 nodes booted... Lab is ready").
3. **Given** a running lab, **When** the user says "Stop all labs", **Then** NetClaw confirms the action, stops all labs, and reports completion.
4. **Given** GNS3 is configured, **When** the user asks about GNS3 projects, **Then** NetClaw lists GNS3 projects with their status.

---

### User Story 3 - Voice-Driven Configuration Analysis (Priority: P1)

An engineer troubleshooting an issue needs to quickly check specific configuration elements (BGP neighbors, OSPF adjacencies, interface configs) without accessing a terminal.

**Why this priority**: Configuration queries are fundamental to troubleshooting. High-frequency use case.

**Independent Test**: Can be tested by asking "Show me BGP neighbors on router R1" and receiving accurate neighbor state information.

**Acceptance Scenarios**:

1. **Given** pyATS connectivity to devices, **When** the user says "Show me BGP neighbors on the core router", **Then** NetClaw queries the device, parses BGP neighbor table, and speaks neighbor IPs, AS numbers, and states.
2. **Given** OSPF is configured, **When** the user asks "Are all OSPF adjacencies up?", **Then** NetClaw checks all OSPF neighbors and reports any that are not in FULL state.
3. **Given** a specific interface, **When** the user asks "What's the status of interface GigabitEthernet0/1 on switch SW1?", **Then** NetClaw reports admin state, protocol state, IP address, and error counters.
4. **Given** the user asks about VLANs, **When** they say "List VLANs on the access switch", **Then** NetClaw retrieves and speaks VLAN IDs and names.

---

### User Story 4 - Incident Management via Voice (Priority: P2)

An on-call engineer receives a page and wants to check incident details and acknowledge the alert without opening their laptop.

**Why this priority**: Critical for on-call workflows. Reduces mean-time-to-acknowledge (MTTA).

**Independent Test**: Can be tested by asking "What incidents are active?" and receiving accurate PagerDuty data.

**Acceptance Scenarios**:

1. **Given** PagerDuty is configured, **When** the user asks "Are there any active incidents?", **Then** NetClaw retrieves and speaks incident titles, priorities, and how long they've been open.
2. **Given** an active incident, **When** the user says "Acknowledge the high priority incident", **Then** NetClaw acknowledges it in PagerDuty and confirms the action.
3. **Given** multiple incidents, **When** the user says "Give me incident details for the database alert", **Then** NetClaw provides incident timeline, assignee, and recent notes.

---

### User Story 5 - RFC and Documentation Lookup (Priority: P2)

An engineer needs to quickly reference an RFC or compliance requirement during a discussion or troubleshooting session.

**Why this priority**: Valuable for technical discussions and compliance verification. Less frequent but high value.

**Independent Test**: Can be tested by asking "What does RFC 4271 say about BGP route selection?" and receiving relevant information.

**Acceptance Scenarios**:

1. **Given** the RFC MCP is available, **When** the user asks "Look up RFC 2328", **Then** NetClaw retrieves the RFC title and provides a brief summary of OSPF version 2.
2. **Given** a specific section is needed, **When** the user asks "What does RFC 4271 say about the decision process?", **Then** NetClaw reads the relevant section in voice-friendly format.
3. **Given** the user asks about compliance, **When** they say "Check if my BGP config follows RFC best practices", **Then** NetClaw runs validation and reports compliance status.

---

### User Story 6 - Memory and Context Queries (Priority: P2)

An engineer wants to recall previous decisions, stored facts, or query NetClaw's memory about past interactions.

**Why this priority**: Leverages Memory MCP for institutional knowledge. Useful for team continuity.

**Independent Test**: Can be tested by asking "What did we decide about the VLAN numbering scheme?" and receiving stored context.

**Acceptance Scenarios**:

1. **Given** facts are stored in Memory MCP, **When** the user asks "What do you remember about the data center migration?", **Then** NetClaw retrieves and speaks relevant stored facts.
2. **Given** a decision was recorded, **When** the user asks "Why did we choose OSPF over EIGRP?", **Then** NetClaw retrieves and explains the recorded decision rationale.
3. **Given** the user wants to store information, **When** they say "Remember that the maintenance window is Sundays 2-4 AM", **Then** NetClaw stores the fact and confirms.

---

### User Story 7 - Proactive Outbound Alerts (Priority: P2)

NetClaw proactively calls the on-call engineer when critical events occur, rather than waiting for them to check.

**Why this priority**: Transforms NetClaw from reactive to proactive. High value for critical infrastructure.

**Independent Test**: Can be tested by triggering a critical alert and verifying NetClaw initiates an outbound call with event details.

**Acceptance Scenarios**:

1. **Given** a critical PagerDuty incident triggers, **When** alert thresholds are exceeded, **Then** NetClaw calls the designated number and speaks the incident details.
2. **Given** a CML lab unexpectedly stops, **When** the lab was marked as "keep running", **Then** NetClaw calls to notify the owner.
3. **Given** network device goes unreachable, **When** pyATS health check fails, **Then** NetClaw calls with device name and last known state.
4. **Given** the call is answered, **When** the engineer asks follow-up questions, **Then** NetClaw provides context and can take actions (acknowledge, restart, etc.).

---

### User Story 8 - Multi-Turn Conversation with Context (Priority: P2)

An engineer has an extended troubleshooting session, asking multiple related questions without repeating context.

**Why this priority**: Natural conversation flow improves usability. Reduces frustration with voice interfaces.

**Independent Test**: Can be tested by asking "Check router R1" then "What about its BGP neighbors?" (without repeating "R1") and receiving correct contextual response.

**Acceptance Scenarios**:

1. **Given** the user previously asked about "router R1", **When** they follow up with "What's its uptime?", **Then** NetClaw understands "its" refers to R1 and provides the answer.
2. **Given** a multi-step troubleshooting flow, **When** the user says "Check the interface I mentioned earlier", **Then** NetClaw recalls the previously discussed interface.
3. **Given** a long call, **When** the user says "Summarize what we've found", **Then** NetClaw recaps the key findings from the conversation.

---

### User Story 9 - Network Topology Description (Priority: P3)

An engineer wants to understand or describe network topology verbally, since visual diagrams can't be shown over phone.

**Why this priority**: Useful but challenging for voice. Lower frequency use case.

**Independent Test**: Can be tested by asking "Describe my network topology" and receiving an accurate verbal description.

**Acceptance Scenarios**:

1. **Given** topology data is available, **When** the user asks "Describe my network topology", **Then** NetClaw provides a verbal description ("You have 3 core routers connected in a triangle, each connected to 2 distribution switches...").
2. **Given** a specific path is needed, **When** the user asks "How does traffic flow from site A to site B?", **Then** NetClaw describes the path including hops and link types.
3. **Given** the user wants a diagram generated, **When** they say "Create a topology diagram and email it to me", **Then** NetClaw generates the diagram and sends it (if email is configured).

---

### User Story 10 - Twitter Integration via Voice (Priority: P3)

An engineer wants to post a NetClaw update or check Twitter mentions without using the app.

**Why this priority**: Nice-to-have social integration. Lower frequency.

**Independent Test**: Can be tested by saying "Post a tweet about the network upgrade" and verifying the tweet is posted.

**Acceptance Scenarios**:

1. **Given** Twitter is configured, **When** the user says "Post a tweet: Just completed the BGP migration successfully", **Then** NetClaw posts the tweet (with #netclaw) and confirms.
2. **Given** mentions exist, **When** the user asks "Any Twitter mentions?", **Then** NetClaw reads recent mentions with author and content.
3. **Given** a mention requires response, **When** the user says "Reply to the last mention with: Thanks for the feedback!", **Then** NetClaw posts the reply.

---

### Edge Cases

- **Ambiguous commands**: When user says "Check the router" but multiple routers exist, NetClaw asks for clarification: "I found 3 routers. Which one: R1, R2, or R3?"
- **Long-running operations**: When lab startup takes 5+ minutes, NetClaw provides periodic progress updates and offers to call back when complete.
- **Speech recognition failures**: When speech is unclear, NetClaw asks for repetition: "I didn't catch that. Could you repeat your request?"
- **Extended call duration**: At 25 minutes, NetClaw warns and offers to summarize and end or continue.
- **MCP tool failures**: When tools are unavailable, NetClaw explains which capability is down and suggests alternatives.
- **Sensitive information**: NetClaw never speaks credentials, keys, or secrets; offers to send via secure channel instead.
- **Concurrent device queries**: When user asks about multiple devices, NetClaw processes sequentially and reports results per device.
- **Network timeouts**: When device queries timeout, NetClaw reports partial results and identifies which devices failed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept inbound voice calls and route them through the voice processing pipeline.
- **FR-002**: System MUST transcribe user speech to text using speech recognition.
- **FR-003**: System MUST process natural language queries through the AI reasoning engine with access to all MCP tools.
- **FR-004**: System MUST convert AI responses to natural speech using text-to-speech.
- **FR-005**: System MUST maintain conversation context within a single call session.
- **FR-006**: System MUST provide access to pyATS for device health checks, configuration parsing, and test execution.
- **FR-007**: System MUST provide access to CML for lab listing, starting, stopping, and node status queries.
- **FR-008**: System MUST provide access to GNS3 for project and node management.
- **FR-009**: System MUST provide access to PagerDuty for incident queries and acknowledgment.
- **FR-010**: System MUST provide access to RFC MCP for documentation lookups.
- **FR-011**: System MUST provide access to Memory MCP for storing and recalling facts and decisions.
- **FR-012**: System MUST initiate outbound calls for proactive alerts based on configurable triggers.
- **FR-013**: System MUST handle long-running operations by providing progress updates.
- **FR-014**: System MUST format all responses for natural speech (no technical IDs, abbreviations expanded, numbers spoken naturally).
- **FR-015**: System MUST enforce rate limiting to prevent abuse (configurable calls per hour).
- **FR-016**: System MUST validate caller identity against a whitelist before processing commands.
- **FR-017**: System MUST log all voice interactions for audit purposes.
- **FR-018**: System MUST handle ambiguous requests by asking clarifying questions.
- **FR-019**: System MUST provide access to Twitter for posting and reading mentions.
- **FR-020**: System MUST describe network topologies verbally when requested.

### Key Entities

- **Voice Session**: Represents an active phone call with context (caller ID, start time, conversation history, current device/lab focus).
- **Voice Command**: A parsed user request with intent, entities (device names, lab names), and parameters.
- **MCP Tool Binding**: Mapping between voice intents and specific MCP tool calls with parameter extraction.
- **Alert Trigger**: Configuration for proactive outbound calls (event type, threshold, recipient phone number).
- **Conversation Context**: Session state including previously mentioned devices, labs, interfaces, and findings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can complete common network queries (health check, BGP status, lab status) in under 60 seconds via voice.
- **SC-002**: System correctly interprets user intent at least 90% of the time on first attempt.
- **SC-003**: Multi-turn conversations maintain correct context for at least 5 consecutive related queries.
- **SC-004**: Proactive alerts reach the on-call engineer within 30 seconds of trigger event.
- **SC-005**: All major MCP integrations (pyATS, CML, GNS3, PagerDuty, RFC, Memory, Twitter) are accessible via voice.
- **SC-006**: Voice response formatting passes readability test (no UUIDs, technical codes, or unpronounceable strings spoken).
- **SC-007**: System handles 10 concurrent voice sessions without degradation.
- **SC-008**: Call transcripts are available for audit within 5 minutes of call completion.
- **SC-009**: Users report voice interface as "useful" or "very useful" in 80% of feedback responses.
- **SC-010**: Average call duration for routine queries is under 3 minutes.

## Assumptions

- Users have the existing Twilio Voice MCP (Feature 042) deployed and functional.
- Users have pyATS configured with device credentials and testbed files for devices they want to query.
- Network devices are reachable from the NetClaw server running pyATS.
- Users have whitelisted phone numbers configured for voice access.
- Twilio account has sufficient credits for voice calls (inbound and outbound).
- Internet connectivity is stable for API calls to MCP servers.
- The AI model (Claude) is available with tool calling capabilities.
- Users accept that some operations may take longer via voice than via CLI.
- Sensitive credentials and secrets are stored securely and never spoken aloud.
- Maximum concurrent call capacity is limited by Twilio account tier and server resources.
- pyATS testbed configuration exists for all devices the user wants to query.
- MCP servers for integrated services (PagerDuty, Memory, RFC, etc.) are already configured.
