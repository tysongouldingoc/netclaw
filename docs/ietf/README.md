# NCFED Internet-Draft — file map

**Submitting to the IETF Datatracker? Upload this file:**

    rendered/draft-capobianco-ncfed-02.xml   ← RFCXML v3, the submission artifact

The Datatracker accepts the XML alone (it renders txt/html server-side). The
companion `rendered/draft-capobianco-ncfed-02.txt` is the human-readable render
of the *same* content — use it for review and sharing, never edit it by hand.

## Layout

| Path | What it is |
|------|------------|
| `draft-capobianco-ncfed-02.md` | **The source of truth.** kramdown-rfc markdown — all edits go here |
| `rendered/draft-capobianco-ncfed-02.xml` | RFCXML **v3** — the Datatracker submission file |
| `rendered/draft-capobianco-ncfed-02.txt` | Text render for humans (generated, do not edit) |
| `render.sh` | Regenerates both `rendered/` files from the `.md` |
| `archive/` | Superseded revisions (`-01` source + renders), kept for the record |
| `captures/` | Packet captures cited in Appendix B (Implementation Status) |
| `SUBMISSION-CHECKLIST.md` | Toolchain + Datatracker submission steps |
| `NCFED-HARDENING-BACKLOG.md` | Findings/backlog feeding the next revision |
| `AGENTPROTO-POSITIONING.md`, `MILESTONE-NOTE.md` | Context notes |

## Editing workflow

1. Edit `draft-capobianco-ncfed-02.md` (never the rendered files — `render.sh`
   overwrites them).
2. Run `./render.sh` from this directory.
3. Commit the `.md` together with both `rendered/` files.

`kdrfc` drops v2 intermediates (`draft-*.xml`, `draft-*.txt`) next to the source;
they are gitignored and `render.sh` deletes them after a successful render. If
you see draft files in *this* directory other than the `.md`, they are stale
intermediates — delete them; the canonical renders live only in `rendered/`.

## Cutting a new revision (-03 and beyond)

1. `git mv` the current `.md` and its two `rendered/` files into `archive/`
   (renders under `archive/rendered/`).
2. Copy the archived `.md` to `draft-capobianco-ncfed-03.md`, bump `docName`
   in the front matter, add a "Changes from" section.
3. Update `DRAFT` in `render.sh`, then follow the editing workflow above.
