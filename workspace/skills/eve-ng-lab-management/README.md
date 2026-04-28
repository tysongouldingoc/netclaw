# EVE-NG Skills Overview

This skill set covers the full EVE-NG workflow in small, focused pieces:

- `eve-ng-lab-management` — platform health, lab inventory, create/delete/export
- `eve-ng-node-operations` — node lifecycle and lab start/stop
- `eve-lab-topology-build` — networks, links, and topology inspection
- `eve-ng-config-ops` — startup config backup, load, and clear
- `eve-ng-console-ops` — live CLI execution on running nodes
- `eve-lab-topology-design` — design planning and `.unl` validation

## Recommended Flow

1. Design or validate the topology.
2. Create the lab.
3. Add nodes.
4. Build the links.
5. Load startup configs if needed.
6. Start nodes.
7. Verify through the console.

## Smoke Test

Run the EVE skill smoke test from the repo root:

```bash
python3 mcp-servers/eve-ng-mcp-server/tests/test_eve_skills_smoke.py
```

The smoke test checks that:
- the EVE skill files exist
- documented MCP tools match the server implementation
- stale local-only references are not present
- the UNL validator script starts successfully
