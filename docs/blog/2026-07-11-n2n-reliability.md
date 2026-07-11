---
title: "Making the mesh hold: N2N federation grows up (async tasks + self-healing)"
date: 2026-07-11
authors: [John, Claude]
status: draft
target: WordPress MCP (present to John for review before publishing — Constitution XVII)
spec: specs/053-n2n-ergonomics/
---

# Making the mesh hold: N2N federation grows up

A few days ago we shipped [N2N federation and the NCFED protocol](2026-07-10-n2n-federation.md) — the ability for independently-run NetClaws to discover each other's skills, invoke each other's tools, and chat claw-to-claw. It worked: John's claw pulled Nick's live CML lab list and Byrn's Nautobot state across the mesh, entirely over federation.

Then we tried to do something ambitious — have one claw *rebuild another operator's entire CML lab* over N2N — and everything fell apart. Not because the protocol was wrong, but because the **operational envelope** was paper-thin. This is the story of hardening it, and it's a good lesson in the difference between "works in the demo" and "works."

## The failures, one after another

Getting three claws (John AS65001, Nick AS65007, Byrn AS65099) to actually cooperate surfaced a parade of issues, each of which took live debugging:

- A **10-node CML lab rebuild dropped mid-flight** with "Connection lost" — the request was one synchronous call that ran the whole multi-minute build, and ngrok reset the long-lived channel before it finished.
- Every time a peer **restarted its daemon**, its channel died and federation silently wedged until someone manually re-dialed — the dead channel lingered as a zombie.
- Every restart also **re-rolled the operator's ngrok endpoint**, so we manually re-exchanged host:port in Slack roughly five times in one afternoon.
- Two claws on **different OpenClaw builds** broke silently: one CLI accepted `--session-key`, the other only `--session-id`; one returned the answer in `payloads[*].text`, the other in `finalAssistantVisibleText`.
- A peer's completed answer **never reached the operator** because the MCP client gave up at 120s while the server ran to 300s.

Each was a real bug. None was in the protocol itself. That's the tell: **the protocol was sound; the resilience wasn't there yet.**

## The fix: stop assuming, start self-healing

We wrote spec 053 — reliability and ergonomics only, with the proven NCFED core (framing, consent, default-deny, no-secrets) explicitly *frozen* — and built six things:

**1. Async task delegation.** Long remote operations are no longer one blocking call. You *submit* a task and get a `task_id` in seconds; the peer runs it in the background; you poll short status calls and fetch the result when it's done. No single call is ever long enough for ngrok to kill. A ten-minute lab build becomes: submit (2s) + a handful of 15s polls + fetch. The task state is persisted, so the result survives a channel drop *and* a daemon restart.

**2. Channel auto-reconnect.** A background supervisor watches every federated peer. When a channel dies — heartbeat misses or a failed send — it's detected, deregistered (no more zombies), and re-established automatically from persisted consent, with bounded backoff. A peer restart now heals itself in under a minute with zero human action.

**3. Endpoint auto-re-announce.** When your ngrok endpoint moves on restart, your claw announces the new endpoint to federated peers over the still-live session, and they re-dial automatically. The manual host:port dance is gone.

**4. Capability negotiation.** Peers exchange a small capability descriptor in the `hello` handshake — protocol version, which agent CLI flag they support, which reply shapes they emit. Each side adapts. A claw on an older build degrades gracefully to the previous behavior instead of breaking. Silent version drift becomes explicit, self-adapting interoperability.

**5. Robustness hardening.** The live hot-patches became first-class, regression-tested requirements: the client always outlasts the server's own timeouts; reply parsing tolerates a trailing log line after the JSON; the HTTP layer reads the full body even when it arrives in separate TCP segments; missing fields return typed errors, not cryptic strings.

**6. Health and one-step setup.** `n2n_health` (and the 3D HUD claw node) show per-peer channel state, last-seen, endpoint freshness, and in-flight tasks with live progress. `n2n_connect` and `n2n_trust` collapse the old five-step setup into one call each.

## What made this work: tests that fail first

Forty-four automated tests now cover the federation layer, most of them driving two services over an in-memory channel pair. They don't just check the happy path — they assert the *guarantees*: that submit returns fast while the op runs long, that a result survives a channel drop and a daemon restart, that a dead channel self-deregisters, that a completed answer is never lost to a timeout mismatch, that a non-federated peer's endpoint update is rejected.

One of those tests immediately earned its keep: it caught a missing `import time` in the reconnect supervisor that would have silently prevented *every* auto-reconnect in production. The whole point of hardening is catching the thing that fails quietly.

## The bigger picture

A community of federated AI network engineers is only as good as its worst 3 a.m. failure mode. The exciting part — "your claw can drive my lab" — is easy to demo and hard to keep running across restarts, moving endpoints, and version drift between independently-operated peers. Spec 053 is the unglamorous work that turns a great demo into something you'd actually leave running. The mesh now holds.

Next: an internal-clutch model (iN2N) for focused single-operator claw fleets, and eventually lifting NCFED into its own protocol repo. But first — the CML lab clone that started all this now completes, cleanly, over the mesh.

---

*Written by John and Claude, with debugging and a sharp `--session-id` catch from Nick, and PR #105 from Byrn. Spec 053, built spec-through-implement over a live three-claw mesh.*
