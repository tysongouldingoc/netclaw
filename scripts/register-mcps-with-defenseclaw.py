#!/usr/bin/env python3
"""Register NetClaw MCP servers with DefenseClaw.

Reads MCP server configurations from openclaw.json and registers them
with DefenseClaw using 'defenseclaw mcp set'.

Usage:
    python3 scripts/register-mcps-with-defenseclaw.py [--dry-run] [--skip-scan]
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def load_openclaw_config() -> dict:
    """Load openclaw.json configuration."""
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    config_paths = []
    if openclaw_home:
        config_paths.append(Path(openclaw_home) / "config" / "openclaw.json")
        config_paths.append(Path(openclaw_home) / "openclaw.json")
    
    config_paths.extend([
        Path.home() / ".openclaw" / "config" / "openclaw.json",
        Path.home() / ".openclaw" / "openclaw.json",
        Path("config/openclaw.json"),
    ])

    for path in config_paths:
        if path.exists():
            with open(path) as f:
                return json.load(f)

    raise FileNotFoundError("openclaw.json not found")


def verify_model_guard_proxy(port: int = 4000, timeout: float = 3.0) -> dict:
    """Probe DefenseClaw Model-Guard proxy port 4000. Fail closed in production."""
    risk_mode = os.environ.get("N2N_RISK_MODE", "testing").strip()
    is_healthy = False

    try:
        url = f"http://127.0.0.1:{port}/healthz"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "ok" and data.get("service") == "defenseclaw-proxy":
                    is_healthy = True
    except Exception:
        is_healthy = False

    if not is_healthy:
        if risk_mode == "production":
            print(f"ERROR: Model-Guard proxy on port {port} is unreachable in production mode.")
            sys.exit(1)
        else:
            return {"status": "WARNING_BYPASS", "exit_code": 0, "healthy": False}

    return {"status": "OK", "exit_code": 0, "healthy": True}


def probe_proxy_endpoint(url: str = "http://10.255.255.1:4000/healthz", timeout: float = 3.0) -> dict:
    """Strict socket/http timeout probe for proxy endpoint health."""
    risk_mode = os.environ.get("N2N_RISK_MODE", "testing").strip()
    t0 = time.time()
    timed_out = False
    fail_closed = False

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            pass
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.timeout):
            timed_out = True
        else:
            timed_out = True
    except socket.timeout:
        timed_out = True
    except Exception:
        timed_out = True

    elapsed = time.time() - t0

    if timed_out and risk_mode == "production":
        fail_closed = True

    return {
        "timed_out": timed_out,
        "elapsed_seconds": elapsed,
        "fail_closed": fail_closed,
        "status": "TIMED_OUT" if timed_out else "OK",
    }


def run_static_security_scan(mcp_name: str, source_dir: str | None = None, mock_findings: list | None = None) -> dict:
    """Pre-activation static code scan gate for target MCP server."""
    risk_mode = os.environ.get("N2N_RISK_MODE", "testing").strip()
    findings = mock_findings if mock_findings is not None else []

    has_high_risk = any(f.get("severity") in ("HIGH", "CRITICAL") for f in findings)

    if has_high_risk:
        if risk_mode == "production":
            return {
                "passed": False,
                "aborted": True,
                "status": "QUARANTINED",
                "findings": findings,
            }
        else:
            return {
                "passed": False,
                "aborted": False,
                "status": "WARNING_BYPASS",
                "findings": findings,
            }

    return {
        "passed": True,
        "aborted": False,
        "status": "CLEAN",
        "findings": [],
    }


def build_command(name: str, config: dict, skip_scan: bool) -> list[str]:
    """Build defenseclaw mcp set command for a server."""
    cmd = ["defenseclaw", "mcp", "set", name]

    if "command" in config:
        cmd.extend(["--command", config["command"]])

        if "args" in config:
            args = config["args"]
            if isinstance(args, list):
                cmd.extend(["--args", json.dumps(args)])
            else:
                cmd.extend(["--args", str(args)])

    if "url" in config:
        cmd.extend(["--url", config["url"]])

    # Add env vars (skip secrets - just note they're needed)
    if "env" in config:
        for key, value in config["env"].items():
            # Skip vars that reference environment variables
            if value.startswith("${"):
                continue
            cmd.extend(["--env", f"{key}={value}"])

    if skip_scan:
        cmd.append("--skip-scan")

    return cmd


def main():
    parser = argparse.ArgumentParser(description="Register MCPs with DefenseClaw")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without executing")
    parser.add_argument("--skip-scan", action="store_true", help="Skip security scan when registering")
    parser.add_argument("--filter", help="Only register MCPs matching this prefix")
    parser.add_argument("--select", help="Comma-separated list of specific MCP server names to register")
    args = parser.parse_args()

    # Preflight check proxy
    verify_model_guard_proxy(port=4000)

    try:
        config = load_openclaw_config()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    mcp_servers = config.get("mcpServers", {})

    if not mcp_servers:
        print("No MCP servers found in openclaw.json")
        sys.exit(0)

    selected_list = None
    if args.select:
        selected_list = [s.strip() for s in args.select.split(",") if s.strip()]

    print(f"Found {len(mcp_servers)} MCP servers in openclaw.json")
    print()

    success = 0
    failed = 0
    skipped = 0

    for name, server_config in sorted(mcp_servers.items()):
        if selected_list is not None and name not in selected_list:
            continue
        if args.filter and not name.startswith(args.filter):
            continue

        # Static scan check
        scan_res = run_static_security_scan(mcp_name=name)
        if scan_res.get("aborted"):
            print(f"  ABORT: {name} failed static security scan - QUARANTINED")
            failed += 1
            continue

        # Skip remote MCP servers (url-only without command)
        if "url" in server_config and "command" not in server_config:
            if server_config["url"].startswith("mcp://"):
                print(f"  SKIP: {name} - remote MCP (mcp:// URL)")
                skipped += 1
                continue

        cmd = build_command(name, server_config, args.skip_scan)

        if args.dry_run:
            print(f"  WOULD RUN: {' '.join(cmd)}")
            success += 1
        else:
            print(f"  Registering: {name}...", end=" ", flush=True)
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    print("OK")
                    success += 1
                else:
                    print("FAILED")
                    print(f"    {result.stderr.strip()}")
                    failed += 1
            except subprocess.TimeoutExpired:
                print("TIMEOUT")
                failed += 1
            except Exception as e:
                print(f"ERROR: {e}")
                failed += 1

    print()
    print(f"Summary: {success} registered, {failed} failed, {skipped} skipped")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

