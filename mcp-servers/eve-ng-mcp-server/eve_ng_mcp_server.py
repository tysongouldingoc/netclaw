#!/usr/bin/env python3
"""
EVE-NG MCP Server - Network lab management via Model Context Protocol.

34 tools across 6 domains:
  System        (3)  — status, auth, list images
  Lab Lifecycle (5)  — list, get, create, delete, export
  Node Ops      (9)  — list, get, create, delete, start, stop, start-lab, stop-lab, wipe
  Network/Topo  (7)  — topology, list-nets, create-net, delete-net, interfaces, connect, node-types
  Console Exec  (6)  — discover, exec-ios, exec-junos, exec-vpcs, exec-eos, exec-nxos
  Config Mgmt   (4)  — get-config, set-config, get-all-configs, wipe-config

Auth: cookie-based session (EVE-NG does not use Bearer tokens).
      Session TTL tracked; re-login triggered on expiry or 401/412.
"""

import json
import logging
import os
import re
import socket
import sys
import time
from functools import wraps
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("eve-ng-mcp")

try:
    import httpx
    from fastmcp import FastMCP
except ImportError as e:
    log.error("Missing required dependency: %s", e)
    log.error("Install with: pip install fastmcp httpx python-dotenv")
    sys.exit(1)

# =============================================================================
# Configuration
# =============================================================================

EVE_URL               = os.getenv("EVE_URL", "http://127.0.0.1")
EVE_USER              = os.getenv("EVE_USER", "")
EVE_PASSWORD          = os.getenv("EVE_PASSWORD", "")
EVE_VERIFY_SSL        = os.getenv("EVE_VERIFY_SSL", "true").lower() == "true"
EVE_SESSION_TTL       = int(os.getenv("EVE_SESSION_TTL", "1800"))   # 30 minutes
EVE_HTML5             = int(os.getenv("EVE_HTML5", "-1"))
EVE_CONSOLE_HOST      = os.getenv("EVE_CONSOLE_HOST", "127.0.0.1")
EVE_CONSOLE_USER      = os.getenv("EVE_CONSOLE_USER", "")
EVE_CONSOLE_PASSWORD  = os.getenv("EVE_CONSOLE_PASSWORD", "")

# =============================================================================
# EVE-NG HTTP Client
# =============================================================================

class EVEClient:
    """HTTP client for EVE-NG REST API with cookie-based session caching."""

    RETRYABLE_CODES = {401, 412}

    def __init__(self, base_url: str, username: str, password: str,
                 verify_ssl: bool = True, session_ttl: int = 1800, html5: int = -1):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.html5 = html5
        self.session_ttl = session_ttl
        self._session_expires: float = 0
        self._client = httpx.Client(
            verify=verify_ssl,
            timeout=30.0,
            headers={"Accept": "application/json", "User-Agent": "eve-ng-mcp/1.0"},
        )

    def _login(self):
        """Authenticate and cache session cookie."""
        log.info("Authenticating with EVE-NG...")
        resp = self._client.post(
            f"{self.base_url}/api/auth/login",
            json={"username": self.username, "password": self.password, "html5": self.html5},
        )
        if resp.status_code not in (200, 204):
            raise EVEError("EVE_AUTH_FAILED", f"Login failed: HTTP {resp.status_code}", resp.status_code)
        self._session_expires = time.time() + self.session_ttl
        log.info("EVE-NG authentication successful")

    def _ensure_auth(self):
        if time.time() >= self._session_expires:
            self._login()

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Authenticated request with one auto-retry on session errors."""
        self._ensure_auth()
        url = f"{self.base_url}{path}"
        try:
            resp = self._client.request(method, url, **kwargs)
            if resp.status_code in self.RETRYABLE_CODES:
                log.info("Session error %s — re-authenticating", resp.status_code)
                self._session_expires = 0
                self._login()
                resp = self._client.request(method, url, **kwargs)
            return resp
        except httpx.ConnectError:
            raise EVEError("EVE_UNREACHABLE", f"Cannot connect to EVE-NG at {self.base_url}", -1)
        except httpx.TimeoutException:
            raise EVEError("EVE_UNREACHABLE", "Request to EVE-NG timed out", -1)

    def get(self, path: str, **kw) -> httpx.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw) -> httpx.Response:
        return self.request("POST", path, **kw)

    def put(self, path: str, **kw) -> httpx.Response:
        return self.request("PUT", path, **kw)

    def delete(self, path: str, **kw) -> httpx.Response:
        return self.request("DELETE", path, **kw)


# =============================================================================
# Error Handling
# =============================================================================

class EVEError(Exception):
    """Structured EVE-NG error with code and HTTP status."""

    def __init__(self, error_code: str, message: str, status_code: int = 500):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "success": False,
            "error": self.message,
            "error_code": self.error_code,
            "status_code": self.status_code,
        }


_HTTP_ERROR_MAP = {
    400: "EVE_VALIDATION",
    401: "EVE_AUTH_FAILED",
    404: "EVE_NOT_FOUND",
    409: "EVE_CONFLICT",
    412: "EVE_SESSION_EXPIRED",
    500: "EVE_SERVER_ERROR",
}


def handle_eve_response(response: httpx.Response, success_codes: list | None = None) -> Any:
    """Parse EVE-NG API response. Unwraps the {'status':'success','data':{}} envelope."""
    success_codes = success_codes or [200, 201, 204]
    if response.status_code in success_codes:
        if response.status_code == 204 or not response.content:
            return None
        body = response.json()
        # EVE-NG sometimes returns HTTP 200 with a failure body — check application status.
        if isinstance(body, dict) and body.get("status") == "fail":
            eve_code = body.get("code", "")
            msg = body.get("message") or str(body)
            raise EVEError("EVE_SERVER_ERROR", f"EVE error {eve_code}: {msg}", response.status_code)
        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body

    code = _HTTP_ERROR_MAP.get(response.status_code, "EVE_SERVER_ERROR")
    try:
        body = response.json()
        msg = body.get("message") or body.get("data") or str(body)
        if isinstance(msg, dict):
            msg = json.dumps(msg)
    except Exception:
        msg = response.text or f"HTTP {response.status_code}"
    raise EVEError(code, str(msg), response.status_code)


def success_response(data: Any = None, message: str | None = None, count: int | None = None) -> str:
    result: dict = {"success": True}
    if data is not None:
        result["data"] = data
    if message:
        result["message"] = message
    if count is not None:
        result["count"] = count
    return json.dumps(result, indent=2)


def error_response(error: Exception) -> str:
    if isinstance(error, EVEError):
        return json.dumps(error.to_dict(), indent=2)
    return json.dumps({
        "success": False,
        "error": str(error),
        "error_code": "EVE_SERVER_ERROR",
        "status_code": 500,
    }, indent=2)


# =============================================================================
# GAIT Audit Logging
# =============================================================================

def with_gait_logging(operation: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            log.info("GAIT: Starting %s", operation)
            try:
                result = func(*args, **kwargs)
                log.info("GAIT: Completed %s", operation)
                return result
            except Exception as exc:
                log.error("GAIT: Failed %s — %s", operation, exc)
                raise
        return wrapper
    return decorator


# =============================================================================
# Path and ID Helpers
# =============================================================================

def normalize_lab_path(path: str) -> str:
    """Ensure lab path has leading slash and .unl extension."""
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith(".unl"):
        path += ".unl"
    return path


def normalize_folder_path(path: str) -> str:
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    return path


def collect_labs(client: EVEClient, folder: str = "/") -> list:
    """Recursively collect all .unl lab paths from folder tree."""
    folder = normalize_folder_path(folder)
    try:
        raw = client.get(f"/api/folders{folder}").json()
    except Exception:
        return []
    payload = raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(payload, dict):
        return []
    labs: list = []
    prefix = "" if folder == "/" else folder.rstrip("/")
    for lab in payload.get("labs") or []:
        name = lab.get("file") or lab.get("name", "")
        if name:
            labs.append(f"{prefix}/{name}")
    for sub in payload.get("folders") or []:
        fname = sub.get("name", "")
        if fname and fname not in (".", ".."):
            sub_path = f"/{fname}" if folder == "/" else f"{folder.rstrip('/')}/{fname}"
            labs.extend(collect_labs(client, sub_path))
    return labs


def resolve_node_id(client: EVEClient, lab_path: str, node_ref: str) -> str:
    """Resolve node name or numeric string to numeric ID string."""
    if str(node_ref).isdigit():
        return str(node_ref)
    response = client.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes")
    data = handle_eve_response(response)
    if isinstance(data, dict):
        for nid, node in data.items():
            if isinstance(node, dict) and node.get("name", "").lower() == str(node_ref).lower():
                return str(nid)
        available = [n.get("name", nid) for nid, n in data.items() if isinstance(n, dict)]
    else:
        available = []
    raise EVEError("EVE_NOT_FOUND", f"Node '{node_ref}' not found. Available: {available}", 404)


def resolve_network_id(client: EVEClient, lab_path: str, net_ref: str) -> str:
    """Resolve network name or numeric string to numeric ID string."""
    if str(net_ref).isdigit():
        return str(net_ref)
    response = client.get(f"/api/labs{normalize_lab_path(lab_path)}/networks")
    data = handle_eve_response(response)
    if isinstance(data, dict):
        for nid, net in data.items():
            if isinstance(net, dict) and net.get("name", "").lower() == str(net_ref).lower():
                return str(nid)
        available = [n.get("name", nid) for nid, n in data.items() if isinstance(n, dict)]
    else:
        available = []
    raise EVEError("EVE_NOT_FOUND", f"Network '{net_ref}' not found. Available: {available}", 404)


def node_is_running(node: dict) -> bool:
    try:
        return int(node.get("status", 0)) != 0
    except Exception:
        return False


def ensure_nodes_stopped_for_link_edit(client: EVEClient, lab_path: str, node_refs: list[str], polls: int = 8, interval: float = 2.0) -> dict:
    """Refuse link edits when any referenced node is still running after polling."""
    last = {}
    for _ in range(polls):
        response = client.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes")
        data = handle_eve_response(response)
        if not isinstance(data, dict):
            return {}
        last = data
        by_id = {str(nid): node for nid, node in data.items() if isinstance(node, dict)}
        by_name = {str(node.get("name", "")).lower(): (str(nid), node) for nid, node in data.items() if isinstance(node, dict)}
        running = []
        for ref in node_refs:
            ref_s = str(ref)
            if ref_s.isdigit():
                node = by_id.get(ref_s)
                node_id = ref_s
            else:
                resolved = by_name.get(ref_s.lower())
                if not resolved:
                    continue
                node_id, node = resolved
            if node and node_is_running(node):
                running.append({"node": node.get("name", node_id), "node_id": node_id, "status": node.get("status")})
        if not running:
            return data
        time.sleep(interval)
    names = ", ".join(item["node"] for item in running)
    raise EVEError(
        "EVE_CONFLICT",
        f"Link edits require affected endpoint nodes to be stopped first. Still running: {names}",
        409,
    )


def poll_node_status(client: EVEClient, lab_path: str, node_id: str,
                     expect_running: bool, polls: int = 5, interval: float = 2.0) -> dict:
    """Poll until node reaches expected state. Returns final nodes dict."""
    last: dict = {}
    for _ in range(polls):
        try:
            data = handle_eve_response(client.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes"))
            if isinstance(data, dict):
                last = data
                node = data.get(str(node_id), {})
                if isinstance(node, dict) and node_is_running(node) == expect_running:
                    break
        except Exception:
            pass
        time.sleep(interval)
    return last


def build_verification(action: str, node_id: str, before: dict, after: dict) -> dict:
    bn = before.get(str(node_id), {})
    an = after.get(str(node_id), {})
    before_run = node_is_running(bn) if isinstance(bn, dict) else None
    after_run  = node_is_running(an) if isinstance(an, dict) else None
    verified = bool(after_run) if action == "start" else (after_run is False)
    return {
        "verified": verified,
        "before_running": before_run,
        "after_running": after_run,
        "note": "EVE-NG node status can lag; polling applied after action.",
    }


def get_console_port(client: EVEClient, lab_path: str, node_id: str) -> int:
    """Get console port from node data; fall back to 32768+id formula."""
    try:
        data = handle_eve_response(client.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}"))
        if isinstance(data, dict):
            port = data.get("console")
            if port and int(port) > 0:
                return int(port)
    except Exception:
        pass
    return 32768 + int(node_id)


# =============================================================================
# Console Engine — Telnet Sessions
# =============================================================================

READ_CHUNK = 65535

IOS_PROMPT_RE  = re.compile(r'(?P<prompt>[A-Za-z0-9_.-]+(?:\([^\r\n)]*\))?[>#])\s*$')
VPCS_PROMPT_RE = re.compile(r'VPCS>\s*$')
JUNOS_OP_RE    = re.compile(r'(?m)^[^\r\n\s>]+>\s*$')
JUNOS_CFG_RE   = re.compile(r'(?m)^\[[^\r\n]+\]\s*\n[^\r\n\s#]+#\s*$')
EOS_PROMPT_RE  = re.compile(r'(?P<prompt>[A-Za-z0-9_.-]+(?:\([^\r\n)]*\))?[>#])\s*$')
NXOS_PROMPT_RE = re.compile(r'(?P<prompt>[A-Za-z0-9_.-]+(?:\([^\r\n)]*\))?[>#])\s*$')


class TelnetSession:
    """Raw telnet session for EVE-NG console access."""

    def __init__(self, host: str, port: int, timeout: float = 1.5):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.settimeout(self.timeout)
        try:
            self.sock.connect((self.host, self.port))
        except (ConnectionRefusedError, OSError) as exc:
            raise EVEError("EVE_CONSOLE_TIMEOUT",
                           f"Cannot connect to console {self.host}:{self.port}: {exc}", -2)
        return self

    def __exit__(self, *_):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def recv_all(self, wait: float = 0.7, loops: int = 4) -> str:
        time.sleep(wait)
        out = ""
        for _ in range(loops):
            try:
                data = self.sock.recv(READ_CHUNK)
                if not data:
                    break
                out += data.decode("utf-8", "ignore")
                if len(data) < READ_CHUNK:
                    break
            except Exception:
                break
        return out

    def recv_until(self, pattern, timeout: float = 10.0, poll: float = 0.2) -> str:
        end = time.time() + timeout
        out = ""
        while time.time() < end:
            try:
                data = self.sock.recv(READ_CHUNK)
                if data:
                    out += data.decode("utf-8", "ignore")
                    if pattern.search(out):
                        return out
                    continue
            except socket.timeout:
                pass
            except Exception:
                break
            time.sleep(poll)
        return out

    def send(self, command: str, wait: float = 0.7) -> str:
        self.sock.sendall((command + "\r").encode())
        return self.recv_all(wait=wait)

    def send_until(self, command: str, pattern, timeout: float = 10.0) -> str:
        self.sock.sendall((command + "\r").encode())
        return self.recv_until(pattern, timeout=timeout)


# --- IOS / IOL / IOS-XE ---

def detect_ios_mode(text: str) -> dict:
    for line in reversed([l.strip() for l in text.splitlines() if l.strip()]):
        m = IOS_PROMPT_RE.search(line)
        if not m:
            continue
        p = m.group("prompt")
        if "(config-router)" in p: return {"prompt": p, "mode": "config-router"}
        if "(config-subif)" in p:  return {"prompt": p, "mode": "config-subif"}
        if "(config-if)" in p:     return {"prompt": p, "mode": "config-if"}
        if "(config)" in p:        return {"prompt": p, "mode": "config"}
        if p.endswith("#"):        return {"prompt": p, "mode": "privileged"}
        if p.endswith(">"):        return {"prompt": p, "mode": "exec"}
    return {"prompt": None, "mode": "unknown"}


def bootstrap_ios(session: TelnetSession) -> list:
    transcript = []
    text = session.recv_all(wait=1.0, loops=6)
    transcript.append({"command": None, "output": text, "mode_after": detect_ios_mode(text)})
    if "initial configuration dialog" in text:
        text = session.send("no", wait=0.8)
        transcript.append({"command": "no", "output": text, "mode_after": detect_ios_mode(text)})
    if "terminate autoinstall" in text:
        text = session.send("yes", wait=0.8)
        transcript.append({"command": "yes", "output": text, "mode_after": detect_ios_mode(text)})
    if "Press RETURN to get started" in text:
        text = session.send("", wait=0.8)
        transcript.append({"command": "", "output": text, "mode_after": detect_ios_mode(text)})
    return transcript


def ensure_ios_privileged(session: TelnetSession) -> list:
    transcript = []
    wake = session.send("", wait=0.5)
    mode = detect_ios_mode(wake)
    transcript.append({"command": "", "output": wake, "mode_after": mode})
    if mode["mode"] in ("config-router", "config-subif", "config-if", "config"):
        out = session.send("end", wait=0.7)
        mode = detect_ios_mode(out)
        transcript.append({"command": "end", "output": out, "mode_after": mode})
    if mode["mode"] == "exec":
        out = session.send("enable", wait=0.7)
        mode = detect_ios_mode(out)
        transcript.append({"command": "enable", "output": out, "mode_after": mode})
    out = session.send("terminal length 0", wait=0.7)
    transcript.append({"command": "terminal length 0", "output": out, "mode_after": detect_ios_mode(out)})
    return transcript


def ensure_ios_config(session: TelnetSession) -> list:
    transcript = ensure_ios_privileged(session)
    out = session.send("configure terminal", wait=0.7)
    transcript.append({"command": "configure terminal", "output": out, "mode_after": detect_ios_mode(out)})
    return transcript


def run_ios_command(session: TelnetSession, cmd: str, wait: float = 0.8, timeout: float = 15.0) -> str:
    lower = cmd.strip().lower()
    if lower.startswith("ping ") or lower.startswith("traceroute "):
        return session.send_until(cmd, IOS_PROMPT_RE, timeout=timeout)
    return session.send(cmd, wait=wait)


# --- Junos ---

def detect_junos_mode(text: str) -> dict:
    if JUNOS_CFG_RE.search(text):
        lines = [l.rstrip() for l in text.splitlines() if l.strip()]
        return {"prompt": lines[-1] if lines else None, "mode": "config"}
    m = JUNOS_OP_RE.search(text)
    if m:
        return {"prompt": m.group(0).strip(), "mode": "operational"}
    return {"prompt": None, "mode": "unknown"}


def ensure_junos_operational(session: TelnetSession) -> list:
    transcript = []
    wake = session.send("", wait=0.7)
    mode = detect_junos_mode(wake)
    transcript.append({"command": "", "output": wake, "mode_after": mode})
    if "login:" in wake:
        out = session.send("root", wait=0.8)
        transcript.append({"command": "root", "output": out, "mode_after": detect_junos_mode(out)})
        if "Password:" in out:
            out = session.send("eve-ng", wait=1.0)
            mode = detect_junos_mode(out)
            transcript.append({"command": "<password>", "output": out, "mode_after": mode})
            wake = out
    if wake.strip().endswith("%") or wake.strip().endswith("$"):
        out = session.send("cli", wait=1.0)
        mode = detect_junos_mode(out)
        transcript.append({"command": "cli", "output": out, "mode_after": mode})
    elif mode["mode"] == "config":
        out = session.send("exit configuration-mode", wait=0.8)
        transcript.append({"command": "exit configuration-mode", "output": out,
                            "mode_after": detect_junos_mode(out)})
    out = session.send("set cli screen-length 0", wait=0.8)
    transcript.append({"command": "set cli screen-length 0", "output": out,
                        "mode_after": detect_junos_mode(out)})
    out = session.send("set cli screen-width 0", wait=0.8)
    transcript.append({"command": "set cli screen-width 0", "output": out,
                        "mode_after": detect_junos_mode(out)})
    return transcript


def run_junos_command(session: TelnetSession, cmd: str, timeout: float = 15.0) -> str:
    normalized = cmd.strip()
    lower = normalized.lower()
    if lower.startswith("show ") and "| no-more" not in lower:
        normalized += " | no-more"
    return session.send_until(normalized, JUNOS_OP_RE, timeout=timeout)


# --- Arista EOS ---

def detect_eos_mode(text: str) -> dict:
    for line in reversed([l.strip() for l in text.splitlines() if l.strip()]):
        m = EOS_PROMPT_RE.search(line)
        if not m:
            continue
        p = m.group("prompt")
        if "(config-" in p: return {"prompt": p, "mode": "config-sub"}
        if "(config)" in p:  return {"prompt": p, "mode": "config"}
        if p.endswith("#"):  return {"prompt": p, "mode": "privileged"}
        if p.endswith(">"):  return {"prompt": p, "mode": "exec"}
    return {"prompt": None, "mode": "unknown"}


def ensure_eos_privileged(session: TelnetSession) -> list:
    transcript = []
    wake = session.send("", wait=0.7)
    mode = detect_eos_mode(wake)
    transcript.append({"command": "", "output": wake, "mode_after": mode})
    if ("login:" in wake or "Username:" in wake) and EVE_CONSOLE_USER:
        out = session.send(EVE_CONSOLE_USER, wait=0.8)
        transcript.append({"command": "<username>", "output": out, "mode_after": detect_eos_mode(out)})
    if mode["mode"] in ("config", "config-sub"):
        out = session.send("end", wait=0.7)
        mode = detect_eos_mode(out)
        transcript.append({"command": "end", "output": out, "mode_after": mode})
    if mode["mode"] == "exec":
        out = session.send("enable", wait=0.7)
        mode = detect_eos_mode(out)
        transcript.append({"command": "enable", "output": out, "mode_after": mode})
    out = session.send("terminal length 0", wait=0.7)
    transcript.append({"command": "terminal length 0", "output": out, "mode_after": detect_eos_mode(out)})
    out = session.send("terminal width 512", wait=0.7)
    transcript.append({"command": "terminal width 512", "output": out, "mode_after": detect_eos_mode(out)})
    return transcript


def ensure_eos_config(session: TelnetSession) -> list:
    transcript = ensure_eos_privileged(session)
    out = session.send("configure terminal", wait=0.7)
    transcript.append({"command": "configure terminal", "output": out, "mode_after": detect_eos_mode(out)})
    return transcript


def run_eos_command(session: TelnetSession, cmd: str, wait: float = 0.8, timeout: float = 15.0) -> str:
    lower = cmd.strip().lower()
    if lower.startswith("ping ") or lower.startswith("traceroute "):
        return session.send_until(cmd, EOS_PROMPT_RE, timeout=timeout)
    return session.send(cmd, wait=wait)


# --- Cisco NX-OS ---

def detect_nxos_mode(text: str) -> dict:
    for line in reversed([l.strip() for l in text.splitlines() if l.strip()]):
        m = NXOS_PROMPT_RE.search(line)
        if not m:
            continue
        p = m.group("prompt")
        if "(config-" in p: return {"prompt": p, "mode": "config-sub"}
        if "(config)" in p:  return {"prompt": p, "mode": "config"}
        if p.endswith("#"):  return {"prompt": p, "mode": "privileged"}
        if p.endswith(">"):  return {"prompt": p, "mode": "exec"}
    return {"prompt": None, "mode": "unknown"}


def ensure_nxos_privileged(session: TelnetSession) -> list:
    transcript = []
    wake = session.send("", wait=1.0)
    mode = detect_nxos_mode(wake)
    transcript.append({"command": "", "output": wake, "mode_after": mode})
    if ("login:" in wake or "Login:" in wake) and EVE_CONSOLE_USER:
        out = session.send(EVE_CONSOLE_USER, wait=1.0)
        transcript.append({"command": "<username>", "output": out, "mode_after": detect_nxos_mode(out)})
        if "Password:" in out and EVE_CONSOLE_PASSWORD:
            out = session.send(EVE_CONSOLE_PASSWORD, wait=1.0)
            transcript.append({"command": "<password>", "output": out, "mode_after": detect_nxos_mode(out)})
    # Dismiss first-boot setup wizard
    if ("Do you want to enforce secure password" in wake
            or "Would you like to enter the basic configuration" in wake):
        out = session.send("no", wait=1.0)
        transcript.append({"command": "no", "output": out, "mode_after": detect_nxos_mode(out)})
    if mode["mode"] in ("config", "config-sub"):
        out = session.send("end", wait=0.7)
        mode = detect_nxos_mode(out)
        transcript.append({"command": "end", "output": out, "mode_after": mode})
    out = session.send("terminal length 0", wait=0.7)
    transcript.append({"command": "terminal length 0", "output": out, "mode_after": detect_nxos_mode(out)})
    out = session.send("terminal width 511", wait=0.7)
    transcript.append({"command": "terminal width 511", "output": out, "mode_after": detect_nxos_mode(out)})
    return transcript


def ensure_nxos_config(session: TelnetSession) -> list:
    transcript = ensure_nxos_privileged(session)
    out = session.send("configure terminal", wait=0.7)
    transcript.append({"command": "configure terminal", "output": out, "mode_after": detect_nxos_mode(out)})
    return transcript


def run_nxos_command(session: TelnetSession, cmd: str, wait: float = 0.8, timeout: float = 15.0) -> str:
    lower = cmd.strip().lower()
    if lower.startswith("ping ") or lower.startswith("traceroute "):
        return session.send_until(cmd, NXOS_PROMPT_RE, timeout=timeout)
    return session.send(cmd, wait=wait)


# =============================================================================
# MCP Server + Client Singleton
# =============================================================================

mcp = FastMCP("EVE-NG MCP Server")
_client: Optional[EVEClient] = None


def get_client() -> EVEClient:
    global _client
    if _client is None:
        if not EVE_USER or not EVE_PASSWORD:
            raise EVEError("EVE_AUTH_FAILED",
                           "EVE_USER and EVE_PASSWORD environment variables are required", 401)
        _client = EVEClient(EVE_URL, EVE_USER, EVE_PASSWORD, EVE_VERIFY_SSL, EVE_SESSION_TTL, EVE_HTML5)
    return _client


# =============================================================================
# System Tools
# =============================================================================

@mcp.tool()
@with_gait_logging("eve_status")
def eve_status() -> str:
    """Get EVE-NG system status including version, CPU, memory, and disk."""
    try:
        data = handle_eve_response(get_client().get("/api/status"))
        return success_response(data, "EVE-NG system status retrieved")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_auth")
def eve_auth() -> str:
    """Verify EVE-NG authentication and return current user details."""
    try:
        data = handle_eve_response(get_client().get("/api/auth"))
        return success_response(data, "Authentication verified")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_list_images")
def eve_list_images(node_type: Optional[str] = None) -> str:
    """
    List available node images on the EVE-NG server.

    Args:
        node_type: Optional filter — 'iol', 'qemu', 'dynamips', 'docker', etc.
                   Omit to list all template types.
    """
    try:
        c = get_client()
        path = f"/api/list/{node_type}s/templates/" if node_type else "/api/list/templates/"
        data = handle_eve_response(c.get(path))
        if isinstance(data, dict):
            items = [{"type": k, **(v if isinstance(v, dict) else {"name": v})} for k, v in data.items()]
        elif isinstance(data, list):
            items = data
        else:
            items = [data] if data else []
        return success_response(items, f"Found {len(items)} images", len(items))
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


# =============================================================================
# Lab Lifecycle Tools
# =============================================================================

@mcp.tool()
@with_gait_logging("eve_list_labs")
def eve_list_labs(folder: str = "/") -> str:
    """
    List all labs recursively from a folder.

    Args:
        folder: Root folder to search (default '/')
    """
    try:
        labs = collect_labs(get_client(), folder)
        return success_response(sorted(labs), f"Found {len(labs)} labs", len(labs))
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_get_lab")
def eve_get_lab(lab_path: str) -> str:
    """
    Get lab metadata: description, version, author, and body.

    Args:
        lab_path: Lab path like '/Labs/demo.unl' — folder prefix required when outside root
    """
    try:
        data = handle_eve_response(get_client().get(f"/api/labs{normalize_lab_path(lab_path)}"))
        return success_response(data)
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_create_lab")
def eve_create_lab(
    name: str,
    folder: str = "/",
    description: str = "",
    version: str = "1",
    author: str = "",
) -> str:
    """
    Create a new empty lab file.

    Args:
        name: Lab name without .unl extension (e.g. 'BGP-Test')
        folder: Target folder (default '/')
        description: Lab description
        version: Version string
        author: Author name
    """
    try:
        payload: dict = {
            "name": name,
            "path": normalize_folder_path(folder),
            "version": version,
        }
        if description:
            payload["description"] = description
        if author:
            payload["author"] = author
        data = handle_eve_response(get_client().post("/api/labs", json=payload),
                                   success_codes=[200, 201])
        return success_response(data, f"Lab '{name}' created in {folder}")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_delete_lab")
def eve_delete_lab(lab_path: str) -> str:
    """
    Delete a lab and all its runtime objects. Stop all nodes first.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
    """
    try:
        handle_eve_response(get_client().delete(f"/api/labs{normalize_lab_path(lab_path)}"),
                            success_codes=[200, 204])
        return success_response(message=f"Lab '{lab_path}' deleted")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_export_lab")
def eve_export_lab(lab_path: str) -> str:
    """
    Export a lab as raw .unl XML content (topology backup / sharing).

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
    """
    try:
        c = get_client()
        resp = c.get(f"/api/labs{normalize_lab_path(lab_path)}/export")
        if resp.status_code not in (200, 201):
            handle_eve_response(resp)
        content = resp.text
        return success_response(
            {"content": content, "size_bytes": len(content)},
            f"Lab exported ({len(content)} bytes)",
        )
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


# =============================================================================
# Node Operation Tools
# =============================================================================

@mcp.tool()
@with_gait_logging("eve_list_nodes")
def eve_list_nodes(lab_path: str) -> str:
    """
    List all nodes in a lab with runtime status, type, image, and console port.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
    """
    try:
        data = handle_eve_response(get_client().get(f"/api/labs{normalize_lab_path(lab_path)}/nodes"))
        if not isinstance(data, dict):
            return success_response([], "No nodes found", 0)
        nodes = [
            {
                "id": nid,
                "name": n.get("name"),
                "type": n.get("type"),
                "template": n.get("template"),
                "image": n.get("image"),
                "status": n.get("status"),
                "running": node_is_running(n),
                "console_port": n.get("console"),
                "cpu": n.get("cpu"),
                "ram": n.get("ram"),
            }
            for nid, n in data.items() if isinstance(n, dict)
        ]
        return success_response(nodes, f"Found {len(nodes)} nodes", len(nodes))
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_get_node")
def eve_get_node(lab_path: str, node: str) -> str:
    """
    Get full details for a single node (config, status, interfaces, console).

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name (e.g. 'R1') or numeric ID
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        data = handle_eve_response(c.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}"))
        return success_response(data)
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_create_node")
def eve_create_node(
    lab_path: str,
    name: str,
    node_type: str,
    template: str,
    image: str = "",
    left: int = 100,
    top: int = 100,
    ram: int = 256,
    ethernet: int = 4,
    serial: int = 0,
    console: str = "telnet",
    cpu: int = 1,
    icon: str = "Router.png",
    node_id: int | None = None,
) -> str:
    """
    Add a new node to a lab from a template.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        name: Node name (e.g. 'R1')
        node_type: Node type — 'iol', 'qemu', 'dynamips', 'docker', 'vpcs'
        template: Template name (e.g. 'vios', 'csr1000v', 'iol')
        image: Image filename — uses template default when blank
        left: Canvas X position (pixels)
        top: Canvas Y position (pixels)
        ram: RAM in MB
        ethernet: Number of Ethernet interfaces
        serial: Number of serial interfaces
        console: Console type — 'telnet' or 'vnc'
        cpu: Number of vCPUs
        icon: Canvas icon filename (e.g. 'Router.png', 'Switch.png', 'Server.png')
        node_id: Optional explicit node ID. Use lab-number block IDs on this host, e.g. 801, 802.
    """
    try:
        c = get_client()
        payload: dict = {
            "name": name, "type": node_type, "template": template,
            "left": left, "top": top, "ram": ram,
            "ethernet": ethernet, "serial": serial,
            "console": console, "cpu": cpu, "icon": icon,
        }
        if image:
            payload["image"] = image
        if node_id is not None:
            existing = handle_eve_response(c.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes"))
            if isinstance(existing, dict) and str(node_id) in existing:
                raise EVEError(
                    "EVE_CONFLICT",
                    f"Node ID '{node_id}' already exists in lab '{lab_path}'",
                    409,
                )
            payload["id"] = int(node_id)
        data = handle_eve_response(
            c.post(f"/api/labs{normalize_lab_path(lab_path)}/nodes", json=payload),
            success_codes=[200, 201],
        )
        verify = handle_eve_response(c.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes"))
        resolved_id = None
        if node_id is not None and isinstance(verify, dict) and str(node_id) in verify:
            resolved_id = str(node_id)
        elif isinstance(verify, dict):
            for nid, node in verify.items():
                if isinstance(node, dict) and node.get("name", "").lower() == name.lower():
                    resolved_id = str(nid)
                    break
        if node_id is not None and resolved_id != str(node_id):
            raise EVEError(
                "EVE_SERVER_ERROR",
                f"Node '{name}' was created but did not persist with requested ID '{node_id}'",
                500,
            )
        return success_response({
            "requested_id": node_id,
            "resolved_id": resolved_id,
            "api_result": data,
        }, f"Node '{name}' created")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_delete_node")
def eve_delete_node(lab_path: str, node: str) -> str:
    """
    Remove a node from a lab. Node must be stopped first.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        handle_eve_response(c.delete(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}"),
                            success_codes=[200, 204])
        return success_response({"node_id": node_id}, f"Node '{node}' deleted")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_start_node")
def eve_start_node(lab_path: str, node: str) -> str:
    """
    Start a node and poll to verify it reaches running state.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name (e.g. 'R1') or numeric ID
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        path = normalize_lab_path(lab_path)
        before = handle_eve_response(c.get(f"/api/labs{path}/nodes")) or {}
        handle_eve_response(c.get(f"/api/labs{path}/nodes/{node_id}/start"))
        after = poll_node_status(c, lab_path, node_id, expect_running=True)
        node_info = before.get(str(node_id), {})
        return success_response({
            "node_id": node_id,
            "node_name": node_info.get("name", node) if isinstance(node_info, dict) else node,
            "verification": build_verification("start", node_id, before, after),
        }, "Node started")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_stop_node")
def eve_stop_node(lab_path: str, node: str) -> str:
    """
    Stop a node and poll to verify it reaches stopped state.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name (e.g. 'R1') or numeric ID
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        path = normalize_lab_path(lab_path)
        before = handle_eve_response(c.get(f"/api/labs{path}/nodes")) or {}
        handle_eve_response(c.get(f"/api/labs{path}/nodes/{node_id}/stop"))
        after = poll_node_status(c, lab_path, node_id, expect_running=False)
        node_info = before.get(str(node_id), {})
        return success_response({
            "node_id": node_id,
            "node_name": node_info.get("name", node) if isinstance(node_info, dict) else node,
            "verification": build_verification("stop", node_id, before, after),
        }, "Node stopped")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_start_lab")
def eve_start_lab(lab_path: str) -> str:
    """
    Start all nodes in a lab. Returns per-node results and running/stopped summary.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
    """
    try:
        c = get_client()
        path = normalize_lab_path(lab_path)
        before = handle_eve_response(c.get(f"/api/labs{path}/nodes")) or {}
        steps = []
        for nid, node in (before.items() if isinstance(before, dict) else {}.items()):
            name = node.get("name", nid) if isinstance(node, dict) else nid
            try:
                handle_eve_response(c.get(f"/api/labs{path}/nodes/{nid}/start"))
                steps.append({"node_id": nid, "node_name": name, "ok": True})
            except Exception as exc:
                steps.append({"node_id": nid, "node_name": name, "ok": False, "error": str(exc)})
        time.sleep(3)
        after = handle_eve_response(c.get(f"/api/labs{path}/nodes")) or {}
        running = [n.get("name", nid) for nid, n in after.items()
                   if isinstance(n, dict) and node_is_running(n)]
        stopped  = [n.get("name", nid) for nid, n in after.items()
                   if isinstance(n, dict) and not node_is_running(n)]
        failures = [s["node_name"] for s in steps if not s["ok"]]
        return success_response(
            {"steps": steps, "summary": {"running": running, "stopped": stopped, "failures": failures}},
            f"Start complete: {len(running)} running, {len(stopped)} stopped",
        )
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_stop_lab")
def eve_stop_lab(lab_path: str) -> str:
    """
    Stop all nodes in a lab. Returns per-node results and final summary.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
    """
    try:
        c = get_client()
        path = normalize_lab_path(lab_path)
        before = handle_eve_response(c.get(f"/api/labs{path}/nodes")) or {}
        steps = []
        for nid, node in (before.items() if isinstance(before, dict) else {}.items()):
            name = node.get("name", nid) if isinstance(node, dict) else nid
            try:
                handle_eve_response(c.get(f"/api/labs{path}/nodes/{nid}/stop"))
                steps.append({"node_id": nid, "node_name": name, "ok": True})
            except Exception as exc:
                steps.append({"node_id": nid, "node_name": name, "ok": False, "error": str(exc)})
        time.sleep(2)
        after = handle_eve_response(c.get(f"/api/labs{path}/nodes")) or {}
        running = [n.get("name", nid) for nid, n in after.items()
                   if isinstance(n, dict) and node_is_running(n)]
        stopped  = [n.get("name", nid) for nid, n in after.items()
                   if isinstance(n, dict) and not node_is_running(n)]
        failures = [s["node_name"] for s in steps if not s["ok"]]
        return success_response(
            {"steps": steps, "summary": {"running": running, "stopped": stopped, "failures": failures}},
            f"Stop complete: {len(stopped)} stopped, {len(running)} still running",
        )
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_wipe_node")
def eve_wipe_node(lab_path: str, node: str) -> str:
    """
    Wipe a node to factory defaults — clears NVRAM and startup config.
    Node must be stopped before wiping.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        handle_eve_response(c.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}/wipe"))
        return success_response({"node_id": node_id}, f"Node '{node}' wiped to factory defaults")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


# =============================================================================
# Network / Topology Tools
# =============================================================================

@mcp.tool()
@with_gait_logging("eve_get_topology")
def eve_get_topology(lab_path: str) -> str:
    """
    Get full lab topology: nodes, networks, and all interconnection links.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
    """
    try:
        data = handle_eve_response(get_client().get(f"/api/labs{normalize_lab_path(lab_path)}/topology"))
        return success_response(data)
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_list_networks")
def eve_list_networks(lab_path: str) -> str:
    """
    List all virtual networks (bridges, clouds, physical interfaces) in a lab.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
    """
    try:
        data = handle_eve_response(get_client().get(f"/api/labs{normalize_lab_path(lab_path)}/networks"))
        if not isinstance(data, dict):
            return success_response([], "No networks found", 0)
        networks = [{"id": nid, **net} for nid, net in data.items() if isinstance(net, dict)]
        return success_response(networks, f"Found {len(networks)} networks", len(networks))
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_create_network")
def eve_create_network(
    lab_path: str,
    name: str,
    network_type: str = "bridge",
    visibility: int = 1,
    left: int = 200,
    top: int = 200,
) -> str:
    """
    Create a virtual network in a lab.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        name: Network name (e.g. 'Net1', 'Management', 'WAN')
        network_type: 'bridge' (internal L2), 'ovs', 'pnet0'-'pnet9' (physical uplink),
                      'cloud0'-'cloud9' (cloud/internet bridge)
        visibility: 1 = visible on canvas, 0 = hidden
        left: Canvas X position
        top: Canvas Y position
    """
    try:
        c = get_client()
        payload = {"name": name, "type": network_type, "visibility": visibility,
                   "left": left, "top": top}
        data = handle_eve_response(
            c.post(f"/api/labs{normalize_lab_path(lab_path)}/networks", json=payload),
            success_codes=[200, 201],
        )
        networks = handle_eve_response(c.get(f"/api/labs{normalize_lab_path(lab_path)}/networks"))
        created_id = None
        if isinstance(networks, dict):
            for nid, net in networks.items():
                if isinstance(net, dict) and net.get("name", "").lower() == name.lower():
                    created_id = str(nid)
                    break
        if not created_id:
            raise EVEError(
                "EVE_SERVER_ERROR",
                f"Network '{name}' creation was acknowledged but did not persist in lab topology",
                500,
            )
        return success_response({
            "network_id": created_id,
            "name": name,
            "network_type": network_type,
            "visibility": visibility,
            "left": left,
            "top": top,
            "api_result": data,
        }, f"Network '{name}' created")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_delete_network")
def eve_delete_network(lab_path: str, network: str) -> str:
    """
    Delete a network from a lab. Disconnect all nodes before deleting.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        network: Network name or numeric ID
    """
    try:
        c = get_client()
        net_id = resolve_network_id(c, lab_path, network)
        handle_eve_response(c.delete(f"/api/labs{normalize_lab_path(lab_path)}/networks/{net_id}"),
                            success_codes=[200, 204])
        return success_response(message=f"Network '{network}' deleted")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_list_node_interfaces")
def eve_list_node_interfaces(lab_path: str, node: str) -> str:
    """
    List all interfaces of a node and their current network connections.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        data = handle_eve_response(
            c.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}/interfaces"))
        return success_response(data)
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_connect_interface")
def eve_connect_interface(
    lab_path: str,
    node: str,
    interface_id: int,
    network: str,
) -> str:
    """
    Connect a node interface to a network.
    Stop the node before rewiring to avoid runtime bridge conflicts.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
        interface_id: Interface index — 0 = first (Ethernet0/0), 1 = second, etc.
        network: Target network name or numeric ID
    """
    try:
        c = get_client()
        ensure_nodes_stopped_for_link_edit(c, lab_path, [node])
        node_id = resolve_node_id(c, lab_path, node)
        net_id = resolve_network_id(c, lab_path, network)
        handle_eve_response(
            c.put(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}/interfaces",
                  json={str(interface_id): int(net_id)}))
        interfaces = handle_eve_response(
            c.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}/interfaces"))
        attached = None
        if isinstance(interfaces, dict):
            iface = interfaces.get(str(interface_id)) or interfaces.get(interface_id)
            if isinstance(iface, dict):
                attached = str(iface.get("network_id") or iface.get("network") or "")
            elif isinstance(interfaces.get("ethernet"), list) and 0 <= int(interface_id) < len(interfaces.get("ethernet")):
                eth = interfaces.get("ethernet")[int(interface_id)]
                if isinstance(eth, dict):
                    attached = str(eth.get("network_id") or eth.get("network") or "")
        if attached != str(net_id):
            raise EVEError(
                "EVE_SERVER_ERROR",
                f"Interface {interface_id} of '{node}' did not persist on network '{network}' after API success",
                500,
            )
        return success_response({
            "node": node, "node_id": node_id,
            "interface_id": interface_id,
            "network": network, "network_id": net_id,
        }, f"Interface {interface_id} of '{node}' connected to '{network}'")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_list_node_types")
def eve_list_node_types() -> str:
    """List available node types (templates) installed on the EVE-NG server."""
    try:
        data = handle_eve_response(get_client().get("/api/list/templates/"))
        if isinstance(data, dict):
            types = [{"type": k, **(v if isinstance(v, dict) else {"name": str(v)})}
                     for k, v in data.items()]
        else:
            types = data if isinstance(data, list) else []
        return success_response(types, f"Found {len(types)} node types", len(types))
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


# =============================================================================
# Console Execution Tools
# =============================================================================

@mcp.tool()
@with_gait_logging("eve_discover_node")
def eve_discover_node(lab_path: str, node: str) -> str:
    """
    Resolve a node by name or ID and return its console connection details.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name (e.g. 'R1') or numeric ID
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        data = handle_eve_response(c.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}"))
        port = get_console_port(c, lab_path, node_id)
        return success_response({
            "node_id": node_id,
            "name": data.get("name") if isinstance(data, dict) else node,
            "type": data.get("type") if isinstance(data, dict) else None,
            "status": data.get("status") if isinstance(data, dict) else None,
            "running": node_is_running(data) if isinstance(data, dict) else None,
            "console_host": EVE_CONSOLE_HOST,
            "console_port": port,
            "telnet": f"telnet://{EVE_CONSOLE_HOST}:{port}",
        })
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_exec_ios")
def eve_exec_ios(
    lab_path: str,
    node: str,
    commands: list[str],
    config_mode: bool = False,
    save: bool = False,
    command_timeout: float = 15.0,
    wait: float = 0.8,
) -> str:
    """
    Execute commands on an IOS / IOL / IOS-XE node via telnet console.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
        commands: Commands to run (e.g. ['show ip route', 'show interfaces'])
        config_mode: Enter global config mode before running (for config commands)
        save: Run 'write memory' after all commands
        command_timeout: Seconds to wait for each command's output (default 15)
        wait: Inter-command pause in seconds (default 0.8)
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        port = get_console_port(c, lab_path, node_id)
        transcript: list = []
        with TelnetSession(EVE_CONSOLE_HOST, port) as sess:
            transcript.extend(bootstrap_ios(sess))
            if config_mode:
                transcript.extend(ensure_ios_config(sess))
            else:
                transcript.extend(ensure_ios_privileged(sess))
            for cmd in commands:
                out = run_ios_command(sess, cmd, wait=wait, timeout=command_timeout)
                transcript.append({"command": cmd, "output": out, "mode_after": detect_ios_mode(out)})
            transcript.extend(ensure_ios_privileged(sess))
            if save:
                out = sess.send("write memory", wait=2.0)
                transcript.append({"command": "write memory", "output": out,
                                   "mode_after": detect_ios_mode(out)})
        return success_response({"node_id": node_id, "node": node,
                                  "config_mode": config_mode, "saved": save,
                                  "transcript": transcript})
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_exec_junos")
def eve_exec_junos(
    lab_path: str,
    node: str,
    commands: list[str],
    command_timeout: float = 15.0,
    wait: float = 0.8,
) -> str:
    """
    Execute operational mode commands on a Junos node via telnet console.
    'show' commands get '| no-more' appended automatically.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
        commands: Junos operational commands (e.g. ['show route', 'show interfaces terse'])
        command_timeout: Seconds to wait for each command's output (default 15)
        wait: Not used for Junos (prompt-based timing), kept for API consistency
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        port = get_console_port(c, lab_path, node_id)
        transcript: list = []
        with TelnetSession(EVE_CONSOLE_HOST, port) as sess:
            transcript.extend(ensure_junos_operational(sess))
            for cmd in commands:
                out = run_junos_command(sess, cmd, timeout=command_timeout)
                transcript.append({"command": cmd, "output": out, "mode_after": detect_junos_mode(out)})
        return success_response({"node_id": node_id, "node": node, "transcript": transcript})
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_exec_vpcs")
def eve_exec_vpcs(
    lab_path: str,
    node: str,
    commands: list[str],
    command_timeout: float = 8.0,
    dhcp_timeout: float = 10.0,
    prompt_timeout: float = 5.0,
) -> str:
    """
    Execute commands on a VPCS node via telnet console.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
        commands: VPCS commands (e.g. ['ip dhcp', 'show ip', 'ping 10.0.0.1'])
        command_timeout: Seconds to wait for command output
        dhcp_timeout: Extra wait seconds for 'ip dhcp' command
        prompt_timeout: Seconds to wait for initial VPCS> prompt
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        port = get_console_port(c, lab_path, node_id)
        transcript: list = []
        with TelnetSession(EVE_CONSOLE_HOST, port) as sess:
            banner = sess.recv_until(VPCS_PROMPT_RE, timeout=prompt_timeout)
            if not VPCS_PROMPT_RE.search(banner):
                banner += sess.send("", wait=0.8)
            transcript.append({"command": None, "output": banner})
            for cmd in commands:
                timeout = dhcp_timeout if cmd.strip() == "ip dhcp" else command_timeout
                out = sess.send_until(cmd, VPCS_PROMPT_RE, timeout=timeout)
                transcript.append({"command": cmd, "output": out})
        return success_response({"node_id": node_id, "node": node, "transcript": transcript})
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_exec_eos")
def eve_exec_eos(
    lab_path: str,
    node: str,
    commands: list[str],
    config_mode: bool = False,
    save: bool = False,
    command_timeout: float = 15.0,
    wait: float = 0.8,
) -> str:
    """
    Execute commands on an Arista EOS node via telnet console.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
        commands: EOS commands (e.g. ['show ip bgp summary', 'show interfaces status'])
        config_mode: Enter global config mode before running
        save: Run 'copy running-config startup-config' after commands
        command_timeout: Seconds to wait for each command's output
        wait: Inter-command pause in seconds
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        port = get_console_port(c, lab_path, node_id)
        transcript: list = []
        with TelnetSession(EVE_CONSOLE_HOST, port) as sess:
            if config_mode:
                transcript.extend(ensure_eos_config(sess))
            else:
                transcript.extend(ensure_eos_privileged(sess))
            for cmd in commands:
                out = run_eos_command(sess, cmd, wait=wait, timeout=command_timeout)
                transcript.append({"command": cmd, "output": out, "mode_after": detect_eos_mode(out)})
            transcript.extend(ensure_eos_privileged(sess))
            if save:
                out = sess.send("copy running-config startup-config", wait=3.0)
                transcript.append({"command": "copy running-config startup-config", "output": out,
                                   "mode_after": detect_eos_mode(out)})
        return success_response({"node_id": node_id, "node": node,
                                  "config_mode": config_mode, "saved": save,
                                  "transcript": transcript})
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_exec_nxos")
def eve_exec_nxos(
    lab_path: str,
    node: str,
    commands: list[str],
    config_mode: bool = False,
    save: bool = False,
    command_timeout: float = 15.0,
    wait: float = 0.8,
) -> str:
    """
    Execute commands on a Cisco NX-OS node via telnet console.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
        commands: NX-OS commands (e.g. ['show ip route', 'show vlan brief'])
        config_mode: Enter global config mode before running
        save: Run 'copy running-config startup-config' after commands
        command_timeout: Seconds to wait for each command's output
        wait: Inter-command pause in seconds
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        port = get_console_port(c, lab_path, node_id)
        transcript: list = []
        with TelnetSession(EVE_CONSOLE_HOST, port) as sess:
            if config_mode:
                transcript.extend(ensure_nxos_config(sess))
            else:
                transcript.extend(ensure_nxos_privileged(sess))
            for cmd in commands:
                out = run_nxos_command(sess, cmd, wait=wait, timeout=command_timeout)
                transcript.append({"command": cmd, "output": out, "mode_after": detect_nxos_mode(out)})
            transcript.extend(ensure_nxos_privileged(sess))
            if save:
                out = sess.send("copy running-config startup-config", wait=3.0)
                transcript.append({"command": "copy running-config startup-config", "output": out,
                                   "mode_after": detect_nxos_mode(out)})
        return success_response({"node_id": node_id, "node": node,
                                  "config_mode": config_mode, "saved": save,
                                  "transcript": transcript})
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


# =============================================================================
# Config Management Tools
# =============================================================================

@mcp.tool()
@with_gait_logging("eve_get_node_config")
def eve_get_node_config(lab_path: str, node: str) -> str:
    """
    Get the stored startup configuration for a node.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        data = handle_eve_response(
            c.get(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}/configs"))
        return success_response({"node_id": node_id, "node": node, "config": data})
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_set_node_config")
def eve_set_node_config(lab_path: str, node: str, config: str) -> str:
    """
    Push a startup configuration to a node. Node should be stopped.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
        config: Full configuration text to store as startup config
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        handle_eve_response(
            c.put(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}/configs",
                  json={"id": int(node_id), "data": config}))
        return success_response({"node_id": node_id, "node": node},
                                f"Config applied to node '{node}'")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_get_all_configs")
def eve_get_all_configs(lab_path: str) -> str:
    """
    Retrieve startup configurations for all nodes in a lab at once.
    Useful for lab-wide config backup before changes.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
    """
    try:
        c = get_client()
        path = normalize_lab_path(lab_path)
        nodes = handle_eve_response(c.get(f"/api/labs{path}/nodes")) or {}
        configs = handle_eve_response(c.get(f"/api/labs{path}/configs")) or {}
        result = [
            {
                "node_id": nid,
                "name": node.get("name") if isinstance(node, dict) else nid,
                "config": configs.get(str(nid), "") if isinstance(configs, dict) else "",
            }
            for nid, node in nodes.items() if isinstance(node, dict)
        ]
        return success_response(result, f"Configs retrieved for {len(result)} nodes", len(result))
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


@mcp.tool()
@with_gait_logging("eve_wipe_node_config")
def eve_wipe_node_config(lab_path: str, node: str) -> str:
    """
    Clear the startup configuration of a node (writes empty string).
    Lighter than eve_wipe_node — config only, no NVRAM wipe. Node must be stopped.

    Args:
        lab_path: Lab path like '/Labs/demo.unl'
        node: Node name or numeric ID
    """
    try:
        c = get_client()
        node_id = resolve_node_id(c, lab_path, node)
        handle_eve_response(
            c.put(f"/api/labs{normalize_lab_path(lab_path)}/nodes/{node_id}/configs",
                  json={"id": int(node_id), "data": ""}))
        return success_response({"node_id": node_id, "node": node},
                                f"Startup config cleared for node '{node}'")
    except EVEError as e:
        return error_response(e)
    except Exception as e:
        return error_response(e)


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    log.info("EVE-NG MCP Server starting")
    log.info("EVE URL:          %s", EVE_URL)
    log.info("EVE User:         %s", EVE_USER)
    log.info("Console host:     %s", EVE_CONSOLE_HOST)
    log.info("Session TTL:      %ss", EVE_SESSION_TTL)
    log.info("SSL verification: %s", EVE_VERIFY_SSL)
    mcp.run(transport="stdio")
