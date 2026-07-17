# Feature Specification: NCFED Post-060 Wire-Confidentiality & Metadata Hardening

**Feature Branch**: `063-ncfed-wire-hardening`
**Created**: 2026-07-17
**Status**: Draft
**Input**: Hardening the real, observed behavior of the certificate-secured NCFED channel (spec 060) after a live two-operator packet capture.

## Problem Statement

Spec 060 put the eN2N NCFED channel under TLS. A live packet capture between two independent operators (Nicholas, AS 65007, capturing his federated session with Byrn, AS 65099, domain `netclaw.byrnbaker.me`; `captures/n2n-encrypted-20260717.pcap`) confirmed the win — TLS 1.3 + AES-256-GCM, and **zero JSON-RPC leakage** versus total plaintext leakage in the pre-060 capture. It also surfaced four concrete follow-ups, all grounded in observed wire behavior rather than hypotheticals:

1. **Endpoint staleness (a confirmed bug).** An operator-initiated connect dials a peer's freshly-advertised address but never records it, so after any reconnect the system falls back to the peer's stale address and fails — forcing a manual re-dial every time a peer's tunnel address rotates.
2. **Mesh-layer confidentiality.** The routing/discovery layer that rides alongside the federation channel is still cleartext; it happens to travel inside the tunnel provider's own encryption today, but that is incidental, not a guarantee the protocol makes.
3. **Metadata exposure.** Even with the payload encrypted, a passive observer can still read each peer's numeric identity (from the cleartext discrimination preamble) and each peer's claw domain (from the TLS server-name indication), letting them map who federates with whom.
4. **Post-quantum posture is undefined.** One side offered a hybrid post-quantum key exchange; the peer's stack declined it and classical key exchange was used. There is no stated posture for whether PQ is expected, and operators cannot see which key exchange a given channel actually negotiated.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Peers reconnect to the current address automatically (Priority: P1)

As a claw operator whose peers are reached over tunnels with rotating addresses, when I (or a peer) provide a new reachable address once, I want my claw to remember it and reconnect there automatically — so I never have to manually re-dial the same peer every time its tunnel address changes.

**Why this priority**: This is a confirmed, repeatedly-hit bug that makes day-to-day federation fragile; it is the highest-value, lowest-risk fix and unblocks reliable operation of everything 060 built.

**Independent Test**: Give the claw a peer's new address once; drop the channel and restart the claw; confirm it reconnects to the new address with no operator action, and that a peer that announces a new address over its authenticated channel is likewise reconnected to automatically.

**Acceptance Scenarios**:

1. **Given** a federated peer whose stored address is stale, **When** the operator supplies the peer's current address once, **Then** the claw connects **and** records that address, so a later automatic reconnect uses it (not the stale one).
2. **Given** a live authenticated channel, **When** the peer announces a new reachable address, **Then** the claw records it and future reconnects target the new address.
3. **Given** the claw restarts after (1) or (2), **When** the reconnect supervisor runs, **Then** it dials the most recently known address with zero manual intervention.
4. **Given** a peer whose address has NOT changed, **When** anything reconnects, **Then** behavior is unchanged (no regression, no spurious address churn).

---

### User Story 2 - The routing layer is confidential on untrusted paths (Priority: P2)

As a claw operator federating across the public internet, I want the peer-discovery/routing layer that accompanies my federation channel to be confidential and its trust boundary explicit — so a passive observer on an untrusted path cannot read my routing/keepalive traffic, and so the protocol's guarantee doesn't silently depend on whichever tunnel happens to be in front of it.

**Why this priority**: It's a genuine confidentiality gap on untrusted paths, but lower urgency than P1 because in the reference deployment the traffic currently rides inside the tunnel provider's encryption; the decision here is partly "specify the guarantee" and partly "close the gap."

**Independent Test**: On a path where the tunnel provider's encryption is removed/observed, confirm the routing layer is either encrypted by the protocol itself or explicitly documented as requiring an encrypted underlay, with a stated trust boundary an operator can verify.

**Acceptance Scenarios**:

1. **Given** a routing/keepalive exchange on an untrusted path, **When** a passive observer captures it, **Then** either the exchange is unreadable, or the protocol's documentation states clearly that confidentiality depends on a named encrypted underlay the operator must provide.
2. **Given** an operator reading the protocol's security documentation, **When** they assess the mesh layer, **Then** the trust boundary (what is protected, by what, on which leg) is unambiguous.

---

### User Story 3 - Federation metadata is minimized (Priority: P3)

As a claw operator, I want the amount of identity metadata visible to a passive observer minimized — specifically the peer identities in the pre-encryption discrimination preamble and the claw domain in the TLS server-name indication — so an eavesdropper cannot trivially enumerate the federation graph (who peers with whom), while any residual exposure that must remain is explicitly documented.

**Why this priority**: Real but lower-severity than confidentiality of content or reliable connectivity; and some exposure is structurally required (the preamble must still discriminate the shared listening port), so this is partly reduction and partly honest documentation.

**Independent Test**: Capture a fresh connection on an untrusted path and confirm the claw domain is no longer in the clear where the mechanism allows (e.g., encrypted server-name), and that any identity signal that must remain cleartext is the minimum necessary and documented as accepted.

**Acceptance Scenarios**:

1. **Given** a new secured connection, **When** a passive observer inspects the handshake, **Then** the peer's claw domain is not readable when the environment supports concealing it, and the design documents whether/when it can be concealed.
2. **Given** the pre-encryption discrimination step, **When** reviewed, **Then** the identity it exposes is the minimum required to route the shared port, and any residual (e.g., numeric identity) is explicitly recorded as accepted exposure with its rationale.

---

### User Story 4 - Post-quantum posture is defined and visible (Priority: P4)

As a claw operator, I want a defined stance on post-quantum key exchange — whether it is offered, preferred, or required — and I want to see, per channel, which key exchange was actually negotiated, so I know whether a given federation link is post-quantum protected or fell back to classical.

**Why this priority**: Forward-looking hardening; classical key exchange is not broken today, so this is about posture and visibility rather than closing an active hole.

**Independent Test**: Open channels to a PQ-capable and a PQ-incapable peer; confirm the negotiated key-exchange group is shown to the operator for each, and that the configured posture (offer / prefer / require) is honored.

**Acceptance Scenarios**:

1. **Given** a peer whose stack supports the hybrid PQ key exchange, **When** the channel establishes, **Then** the negotiated group is the hybrid and the operator can see that it is.
2. **Given** a peer whose stack does not support it, **When** the channel establishes under the default posture, **Then** it falls back to classical and the operator can see the classical group was used.
3. **Given** an operator who sets a "require PQ" posture, **When** a non-PQ peer connects, **Then** the outcome matches the documented policy for that posture (refuse, or warn-and-allow, per the resolved decision).

---

### Edge Cases

- **Both operator dial and peer announcement disagree on an address**: the most recent, successfully-usable address wins; a persisted address that fails should not permanently mask a newer working one.
- **A malicious or mistaken endpoint announcement**: an address update accepted over a channel MUST be bound to that authenticated peer's identity (a peer cannot move another peer's address), consistent with the existing authenticated-channel rules.
- **Concealing the claw domain isn't supported end-to-end** (the mechanism needs supporting infrastructure that may be absent): the claw must degrade cleanly to the current behavior and document that the domain remains visible in that case, never fail the connection over it.
- **Preamble minimization must not break shared-port discrimination**: any change to what the preamble exposes must still let the shared port distinguish this protocol from the others it coexists with.
- **PQ "require" against a classical-only mesh**: the posture must have a defined, non-silent outcome so an operator isn't surprised by a dropped peer.

## Requirements *(mandatory)*

### Functional Requirements

**Endpoint persistence (P1)**

- **FR-001**: An operator-initiated connect to a peer MUST persist that peer's supplied reachable address to the peer's durable record, so a later automatic reconnect targets it.
- **FR-002**: A reachable-address announcement received from a peer over its authenticated channel MUST persist to that peer's record, bound to the authenticated peer identity (a peer cannot change another peer's address).
- **FR-003**: The automatic reconnect supervisor MUST use the most recently persisted address for a peer, and MUST NOT fall back to a stale address once a newer one is known.
- **FR-004**: These changes MUST NOT alter behavior when a peer's address is unchanged (no address churn, no re-consent, no regression to existing federation).

**Mesh-layer confidentiality (P2)**

- **FR-005**: The peer-discovery/routing layer that accompanies the federation channel MUST NOT be trivially readable by a passive observer on an untrusted path; the protocol MUST either protect it directly or REQUIRE (and document) a named encrypted underlay for untrusted paths.
- **FR-006**: The trust boundary for the mesh layer (what is protected, by which mechanism, on which network leg) MUST be documented so an operator can verify it, rather than depending implicitly on an incidental transport.

**Metadata minimization (P3)**

- **FR-007**: Where the environment supports it, the peer's claw domain MUST NOT be exposed in the clear during connection establishment; when it cannot be concealed, the claw MUST proceed and the exposure MUST be documented as a known residual.
- **FR-008**: The pre-encryption discrimination step MUST expose no more identity metadata than is strictly required to route the shared listening port; any identity that must remain in the clear MUST be documented as accepted exposure with rationale.
- **FR-009**: Metadata-minimization changes MUST NOT break shared-port discrimination or federation with peers that do not implement the minimization.

**Post-quantum posture (P4)**

- **FR-010**: The claw MUST offer a hybrid post-quantum key exchange by default and interoperate with peers that accept it or fall back to classical.
- **FR-011**: The operator MUST be able to configure the PQ posture (at minimum: offered/opportunistic vs. required), and each posture MUST have a defined, non-silent outcome when a peer cannot meet it.
- **FR-012**: The negotiated key-exchange group for each channel MUST be visible to the operator (in the same posture/credential view that already surfaces channel trust), distinguishing a post-quantum-protected channel from a classical one.

**Cross-cutting**

- **FR-013**: All four changes MUST build on the existing 060 mechanisms and durable records (no parallel stores) and MUST NOT weaken the authentication, encryption, or trust guarantees 060 established.
- **FR-014**: Operator-visible signals added here (negotiated KEX group, endpoint freshness) MUST appear in the existing operator posture/HUD surface, not a new one.

### Key Entities

- **Peer record (existing)**: gains reliable, current reachable-address fields that survive reconnects and restarts; extended, not replaced.
- **Channel security facts (existing)**: gains the negotiated key-exchange group and PQ indicator alongside the trust model and credential fields 060 already exposes.
- **Mesh trust boundary (documentation artifact)**: a clear statement of what protects the routing layer on each leg.

## Success Criteria *(mandatory)*

- **SC-001**: After a peer's address is supplied once, an operator performs **zero** manual re-dials of that peer across subsequent reconnects and restarts (measured over a tunnel-address rotation).
- **SC-002**: On an untrusted path with the incidental transport encryption removed, a passive capture of the routing layer yields no readable peer routing/keepalive content — or the documentation unambiguously states the required encrypted underlay, and an operator can point to which mechanism is protecting it.
- **SC-003**: On a fresh secured connection in a supporting environment, a passive capture does not reveal the peer's claw domain; in a non-supporting environment the connection still succeeds and the residual exposure is documented.
- **SC-004**: For any established channel, an operator can determine within one view whether it negotiated post-quantum or classical key exchange, with 100% accuracy against the actual negotiation.
- **SC-005**: Zero regressions: existing federated peers (including those that do not implement any of these changes) continue to federate exactly as before, with no forced re-consent or re-pinning.

## Assumptions

- **Endpoint persistence is the priority and is a pure bug fix** over existing records; it does not require any peer to upgrade and is safe to ship independently of the other three items.
- **The reference deployment reaches peers over tunnels whose addresses rotate**; "reachable address" means whatever the operator/peer currently advertises (e.g., a tunnel host:port), and identity remains the stable peer identity, not the address (consistent with 060/059).
- **The discrimination preamble must remain able to distinguish this protocol on the shared port**; therefore some minimal pre-encryption signal is structurally unavoidable, and full preamble concealment is out of scope — the goal is minimization plus honest documentation.
- **Concealing the TLS server name depends on supporting infrastructure** that may not be universally available; the design treats concealment as best-effort with clean fallback, not a hard requirement that could break connectivity.
- **Post-quantum availability depends on both peers' underlying crypto stacks and their versions**; the claw controls only what it offers/prefers/requires, not what a peer supports.
- **No new third-party runtime dependencies are preferred**; mechanisms should reuse what the platform and 060 already provide.
- **The NCFED Internet-Draft revision** reflecting whatever this feature lands is expected later and is explicitly out of scope here.
- **The specific design decisions** — whether the mesh layer is encrypted by the protocol vs. documented-underlay (FR-005/006), how far preamble minimization can go (FR-008), and whether "require PQ" refuses or warns (FR-011) — are deliberately left open for the clarify/plan phase; the spec fixes the required outcomes and visibility, not the mechanism.
