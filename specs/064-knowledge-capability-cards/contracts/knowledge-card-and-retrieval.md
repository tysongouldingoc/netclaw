# Contract: Knowledge on the Capability Card + Retrieval Skill

Two wire contracts, both carried over the existing NCFED channel — no new methods.

## 1. Capability card: `knowledge` array (via `n2n/inventory` / `n2n/inventory_get`)

The card gains a `knowledge` array alongside `skills` / `mcp_servers`. Each element is the
Knowledge Skill entity (data-model.md). Content-free; visibility-filtered per peer.

```json
{
  "identity": "as65001-4.4.4.4",
  "version": 42,
  "skills": [ ... ],
  "mcp_servers": [ ... ],
  "knowledge": [
    {
      "id": "knowledge:documents",
      "name": "Knowledge: documents",
      "description": "Automate Your Network (John Capobianco) — network automation, Ansible, CI/CD NDLC, data models, templates, reconnaissance, automated documentation.",
      "tags": ["install-guide"],
      "doc_count": 1,
      "page_count": 212,
      "chunk_count": 389,
      "retrieval": "n2n-knowledge/query"
    }
  ],
  "badges": [ ... ],
  "posture": { ... },
  "llm": { ... }
}
```

**Rules**
- A peer that does not understand `knowledge` MUST ignore it (backwards compatible, FR/Const XV).
- `description` MAY omit document titles in topic-only mode (D5); everything else unchanged.
- The card MUST still pass `_assert_no_secrets`; `id` is opaque and safe to expose.

## 2. Retrieval: invocable knowledge-retrieval skill (via `n2n/tools/call`)

The `retrieval` name from the card entry is invoked with the advertised `id`.

**Request** (`n2n/tools/call`):

```json
{
  "tool": "n2n-knowledge/query",
  "arguments": {
    "corpus_id": "knowledge:documents",
    "query": "summarize the book's main topics and takeaways",
    "k": 8
  },
  "request_id": "as65099-10.255.255.1:7"
}
```

**Result** (grounded answer with provenance, FR-008):

```json
{
  "answer": "Automate Your Network is ... (grounded summary)",
  "provenance": {
    "peer": "as65001-4.4.4.4",
    "corpus_id": "knowledge:documents",
    "citations": [
      {"title": "Automate Your Network", "loc": "Preface p.13"},
      {"title": "Automate Your Network", "loc": "Summary p.207"}
    ]
  }
}
```

**Rules**
- Default-deny + possession tier: a self-asserted (keyless) or ungranted peer is refused
  with the standard NCFED authorization error and audited (FR-007; NCFED §6.4, §9.3).
- `corpus_id` MUST be one the caller is authorized to see; an unknown/hidden id is answered
  exactly as "no such corpus" (no existence oracle).
- The callee runs `rag_search` against its **live** RAG; the answer is composed by the
  owner's agent and returned with citations when the source provides them.
- One audit record per call: `{peer_identity, corpus_id, request_id, decision, gait_ref}`.

## 3. Routing behavior (agent/router, not a wire message)

Before answering a knowledge/document question the agent MUST:
1. Score the query against all visible advertised collection descriptions (local + peers).
2. If a peer corpus is the best match above threshold → invoke contract #2 against that peer
   and return its answer with provenance.
3. Else if a local corpus matches → answer locally.
4. Else → answer from the model; MUST NOT fabricate a federated source.
Selection is repeatable (stable tiebreak by peer identity then corpus_id).
