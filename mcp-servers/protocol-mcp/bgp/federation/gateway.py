"""Run a local gateway agent turn for N2N delegated chat / skill execution.

OpenClaw's gateway (2026.6+) is WebSocket-only — it does NOT serve an
OpenAI-compatible `/v1/chat/completions` REST route. The correct way to run an
agent turn from outside the gateway is the CLI:

    openclaw agent --agent <id> --session-key <key> --json -m "<prompt>"

which returns a JSON envelope whose reply text is at result.payloads[*].text.
This module wraps that so the federation responder (chat.py, invocation.py) can
generate replies without assuming a REST endpoint that doesn't exist.
"""

import asyncio
import json
import logging
import os

logger = logging.getLogger("n2n.gateway")

AGENT_ID = os.environ.get("N2N_AGENT_ID", "main")


def _extract_reply(stdout: str):
    """Parse the `openclaw agent --json` envelope (which is preceded by banner
    noise) and return (reply_text, tokens_used)."""
    start = stdout.find("{")
    obj = None
    while start != -1:
        try:
            obj = json.loads(stdout[start:])
            break
        except Exception:
            start = stdout.find("{", start + 1)
    if obj is None:
        # No JSON — return raw trailing text so the caller still gets something.
        return stdout.strip()[-2000:], 0

    # Reply text: result.payloads[*].text (concatenated)
    texts = []
    result = obj.get("result", obj)
    for p in (result.get("payloads") or []):
        if isinstance(p, dict) and isinstance(p.get("text"), str):
            texts.append(p["text"])
    reply = "\n".join(t for t in texts if t.strip())
    if not reply:
        # Fallbacks across possible shapes
        for key in ("reply", "text", "message", "output", "response"):
            v = result.get(key)
            if isinstance(v, str) and v.strip():
                reply = v
                break

    # Best-effort token count
    tokens = 0
    try:
        usage = (result.get("meta") or {}).get("usage") or obj.get("usage") or {}
        tokens = usage.get("total_tokens") or usage.get("totalTokens") or 0
    except Exception:
        tokens = 0
    return reply or "(no reply text in agent response)", int(tokens or 0)


async def run_agent_turn(prompt: str, session_key: str = "n2n", timeout_s: int = 300):
    """Run one gateway agent turn. Returns (reply_text, tokens_used).

    Raises TimeoutError on timeout; on non-zero exit returns the stderr tail as
    the reply so the caller can surface a useful message rather than crashing.
    """
    # Use --session-id (supported across OpenClaw CLI versions). Older/newer
    # builds diverge on --session-key vs --session-id; --session-id is the
    # common one (a peer on a build without --session-key errored otherwise).
    cmd = ["openclaw", "agent", "--agent", AGENT_ID,
           "--session-id", session_key, "--json", "-m", prompt]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise
    stdout = out.decode(errors="replace") if out else ""
    if proc.returncode != 0:
        logger.warning("openclaw agent exited %s", proc.returncode)
    return _extract_reply(stdout)
