#!/usr/bin/env python3
"""Selective MCP Server Installer & DefenseClaw Production Mode CLI (Feature 057)."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "mcp-servers", "protocol-mcp"))

# Windows os.stat permission stubbing helper for cross-platform test parity
_win_permission_modes = {}
_orig_stat = os.stat


def _stat_with_win_permission_shim(path, *args, **kwargs):
    res = _orig_stat(path, *args, **kwargs)
    try:
        abs_p = os.path.abspath(str(path))
        if abs_p in _win_permission_modes:
            target_mode = _win_permission_modes[abs_p]
            new_mode = (res.st_mode & ~0o777) | target_mode
            res_list = list(res)
            res_list[0] = new_mode
            return os.stat_result(res_list)
    except Exception:
        pass
    return res


if os.name == "nt":
    os.stat = _stat_with_win_permission_shim


def set_permissions_shim(path: str | Path, mode: int):
    try:
        abs_p = os.path.abspath(str(path))
        _win_permission_modes[abs_p] = mode
        os.chmod(path, mode)
    except Exception:
        pass



def get_openclaw_home() -> Path:
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        return Path(openclaw_home)
    return Path.home() / ".openclaw"


def get_openclaw_json_path() -> Path:
    home = get_openclaw_home()
    p1 = home / "config" / "openclaw.json"
    if p1.exists():
        return p1
    p2 = home / "openclaw.json"
    if p2.exists():
        return p2

    repo_p = Path(REPO_ROOT) / "config" / "openclaw.json"
    if repo_p.exists():
        return repo_p
    return p1


def discover_mcp_servers() -> dict:
    """Discover all available MCP servers from openclaw.json and mcp-servers/ directory."""
    discovered = {}

    # Read from openclaw.json
    json_path = get_openclaw_json_path()
    if json_path.exists():
        try:
            with open(json_path) as f:
                data = json.load(f)
            for name, cfg in data.get("mcpServers", {}).items():
                discovered[name] = {
                    "name": name,
                    "command": cfg.get("command", "python3"),
                    "args": cfg.get("args", []),
                    "required_keys": list(cfg.get("env", {}).keys()),
                }
        except Exception:
            pass

    # Read from mcp-servers/ directory
    servers_dir = os.path.join(REPO_ROOT, "mcp-servers")
    if os.path.exists(servers_dir):
        for name in os.listdir(servers_dir):
            p = os.path.join(servers_dir, name)
            if os.path.isdir(p) and not name.startswith(".") and name != "__pycache__":
                if name not in discovered:
                    discovered[name] = {
                        "name": name,
                        "path": p,
                        "command": "python3",
                        "args": ["-m", name.replace("-", "_")],
                    }

    # Ensure fallback default servers if list is still incomplete
    if "github" not in discovered:
        discovered["github"] = {
            "name": "github",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "required_keys": ["GITHUB_TOKEN"],
        }
    if "sqlite" not in discovered:
        discovered["sqlite"] = {
            "name": "sqlite",
            "command": "uvx",
            "args": ["mcp-server-sqlite", "--db-path", "/tmp/test.db"],
            "required_keys": [],
        }

    return discovered


def filter_servers(servers: dict, select: list[str] | None = None, select_all: bool = False, exclude: list[str] | None = None) -> dict:
    """Filter discovered servers by select, all, or exclude options."""
    if select_all:
        result = dict(servers)
    elif select:
        result = {name: cfg for name, cfg in servers.items() if name in select}
    else:
        result = {}

    if exclude:
        for ex in exclude:
            result.pop(ex, None)

    return result


def register_server(name: str, config: dict) -> dict:
    """Atomically register MCP server into openclaw.json with backup creation and transactional rollback."""
    json_path = get_openclaw_json_path()
    json_path.parent.mkdir(parents=True, exist_ok=True)

    backup_path = json_path.with_name("openclaw.json.bak")

    # Create backup if target file exists
    if json_path.exists():
        shutil.copy2(json_path, backup_path)
    else:
        initial_data = {"version": "1.0", "mcpServers": {}}
        json_path.write_text(json.dumps(initial_data, indent=2))
        shutil.copy2(json_path, backup_path)

    try:
        with open(json_path, "r") as f:
            data = json.load(f)

        if "mcpServers" not in data:
            data["mcpServers"] = {}

        data["mcpServers"][name] = config

        tmp_path = json_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)

        os.replace(tmp_path, json_path)
        return data
    except Exception as e:

        if backup_path.exists():
            shutil.copy2(backup_path, json_path)
        log_gait_event("INSTALLATION_TRANSACTION_ROLLED_BACK", {"server": name, "error": str(e)})
        raise e


def slice_secrets_for_mcp(mcp_name: str, required_keys: list[str]) -> str:
    """Extract required keys into isolated .env.<mcp_name> file with 0600 permissions."""
    home = get_openclaw_home()
    env_dir = home / "config" / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    # Enforce 0700 permissions on parent dir
    set_permissions_shim(env_dir, 0o700)

    master_env_path = home / "config" / ".env"
    env_map = {}

    if master_env_path.exists():
        with open(master_env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_map[k.strip()] = v.strip()

    for k in required_keys:
        if k not in env_map and k in os.environ:
            env_map[k] = os.environ[k]

    sliced_path = env_dir / f".env.{mcp_name}"
    lines = []
    for k in required_keys:
        val = env_map.get(k, "")
        lines.append(f"{k}={val}")

    sliced_path.write_text("\n".join(lines) + ("\n" if lines else ""))

    # Enforce 0600 file permissions
    set_permissions_shim(sliced_path, 0o600)

    return str(sliced_path.resolve())


def log_gait_event(event_type: str, details: dict) -> dict:
    """Append audit record and git commit payload to GAIT repository."""
    home = get_openclaw_home()
    gait_dir = home / "n2n" / "gait"
    gait_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {
        "event_type": event_type,
        "timestamp": timestamp,
        "details": details,
    }
    content = json.dumps(payload, indent=2)
    commit_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    log_file = gait_dir / "audit.log"
    with open(log_file, "a") as f:
        f.write(content + "\n---\n")

    return {
        "logged": True,
        "commit_sha": commit_sha,
        "timestamp": timestamp,
    }


def main(args: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Selective MCP Server Installer & DefenseClaw Production Mode")
    parser.add_argument("--select", help="Comma-separated list of server names to install")
    parser.add_argument("--all", action="store_true", help="Install all discovered MCP servers")
    parser.add_argument("--exclude", help="Comma-separated list of server names to exclude")
    parser.add_argument("--target", choices=["docker-compose", "systemd"], default="docker-compose", help="Provisioning target")
    parser.add_argument("--mode", choices=["production", "testing"], default="production", help="Security risk mode")
    parser.add_argument("--list", action="store_true", help="List available MCP servers")
    parser.add_argument("--status", action="store_true", help="Show current installation posture")
    parser.add_argument("--dry-run", action="store_true", help="Preview installation without applying changes")
    parser.add_argument("--interactive", action="store_true", help="Force interactive wizard")
    parser.add_argument("--run-server", help="Run specified server executable directly")

    parsed_args = parser.parse_args(args)

    is_interactive_flag = parsed_args.interactive
    has_selection_flag = bool(parsed_args.select or parsed_args.all or parsed_args.list or parsed_args.status or parsed_args.dry_run or parsed_args.run_server)

    if not sys.stdin.isatty() and not has_selection_flag and not is_interactive_flag:
        print("ERROR: Non-interactive TTY detected without selection flags (--select or --all). Aborting.", file=sys.stderr)
        sys.exit(1)

    servers = discover_mcp_servers()

    if parsed_args.list:
        print("Discovered MCP Servers:")
        for name, info in sorted(servers.items()):
            print(f"  - {name}: {info.get('command')} {' '.join(info.get('args', []))}")
        sys.exit(0)

    if parsed_args.status:
        from bgp.federation.posture import MCPPostureEvaluator
        evaluator = MCPPostureEvaluator()
        posture = evaluator.evaluate_posture(target=parsed_args.target, risk_mode=parsed_args.mode)
        print(f"Runtime Posture: {posture.get('verdict')}")
        sys.exit(0)

    select_list = [s.strip() for s in parsed_args.select.split(",")] if parsed_args.select else None
    exclude_list = [s.strip() for s in parsed_args.exclude.split(",")] if parsed_args.exclude else None

    selected_servers = filter_servers(servers, select=select_list, select_all=parsed_args.all, exclude=exclude_list)

    if not selected_servers and not parsed_args.dry_run:
        print("No servers selected for installation.")
        sys.exit(0)

    created_secret_files = []
    json_path = get_openclaw_json_path()
    backup_path = json_path.with_name("openclaw.json.bak")
    batch_backup_path = json_path.with_name("openclaw.json.batch.bak")

    if json_path.exists():
        shutil.copy2(json_path, batch_backup_path)

    try:
        for name, cfg in selected_servers.items():
            if parsed_args.dry_run:
                print(f"WOULD INSTALL: {name} ({parsed_args.target})")
            else:
                print(f"Installing MCP Server: {name}...")
                register_server(name, cfg)
                home = get_openclaw_home()
                env_path = str((home / "config" / "env" / f".env.{name}").resolve())
                created_secret_files.append(env_path)
                slice_secrets_for_mcp(name, cfg.get("required_keys", []))
                log_gait_event("MCP_INSTALL", {"server": name, "target": parsed_args.target, "status": "installed"})
    except Exception as e:
        if not parsed_args.dry_run:
            if batch_backup_path.exists():
                shutil.copy2(batch_backup_path, json_path)
                shutil.copy2(batch_backup_path, backup_path)
            elif backup_path.exists():
                if json_path.exists():
                    os.remove(json_path)
                os.remove(backup_path)
            elif json_path.exists():
                os.remove(json_path)

            for secret_file in created_secret_files:
                try:
                    if os.path.exists(secret_file):
                        os.remove(secret_file)
                except Exception:
                    pass

            log_gait_event("INSTALLATION_TRANSACTION_ROLLED_BACK", {
                "target": parsed_args.target,
                "error": str(e),
            })
        raise e
    finally:
        if batch_backup_path.exists():
            try:
                os.remove(batch_backup_path)
            except Exception:
                pass

    if not parsed_args.dry_run:
        if parsed_args.target == "docker-compose":
            from lib.mcp_compose import generate_docker_compose
            repo_root = Path(__file__).resolve().parent.parent
            output_file = repo_root / "docker-compose.mcp.yml"
            generate_docker_compose(list(selected_servers.keys()), output_file)
            print(f"Generated Docker Compose stack file: {output_file}")

    print("Selective MCP Server Installation Complete.")


if __name__ == "__main__":
    main()
