"""Docker Compose generator for hardened MCP servers (Feature 057)."""

import json
import os
from pathlib import Path


def _get_openclaw_json_path() -> Path:
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        p = Path(openclaw_home) / "config" / "openclaw.json"
        if p.exists():
            return p
        p2 = Path(openclaw_home) / "openclaw.json"
        if p2.exists():
            return p2
        return p

    home = Path.home()
    p = home / ".openclaw" / "config" / "openclaw.json"
    if p.exists():
        return p
    p2 = home / ".openclaw" / "openclaw.json"
    if p2.exists():
        return p2

    repo_p = Path(__file__).resolve().parent.parent.parent / "config" / "openclaw.json"
    if repo_p.exists():
        return repo_p
    return p


def get_active_mcp_service_names() -> list[str]:
    """Returns list of active MCP server names from openclaw.json."""
    json_path = _get_openclaw_json_path()
    if not json_path.exists():
        return []
    try:
        with open(json_path) as f:
            data = json.load(f)
        return list(data.get("mcpServers", {}).keys())
    except Exception:
        return []


def get_service_dict(mcp_name: str) -> dict:
    """Returns dictionary representation of a single MCP compose service."""
    return {
        "image": f"mcp-{mcp_name}:latest",
        "container_name": f"mcp-{mcp_name}",
        "security_opt": ["no-new-privileges:true"],
        "read_only": True,
        "cap_drop": ["ALL"],
        "tmpfs": ["/tmp"],
        "env_file": [f"config/env/.env.{mcp_name}"],
        "networks": ["defenseclaw_net"],
    }


def generate_docker_compose_string(selected_mcps: list[str]) -> str:
    """Generates YAML string for docker-compose.mcp.yml with hardened security profile."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    lines = [
        "services:",
    ]
    for mcp in selected_mcps:
        dockerfile_path = repo_root / "mcp-servers" / mcp / "Dockerfile"
        lines.extend([
            f"  {mcp}:",
            f"    image: mcp-{mcp}:latest",
            f"    container_name: mcp-{mcp}",
        ])
        if dockerfile_path.exists():
            lines.extend([
                "    build:",
                f"      context: mcp-servers/{mcp}",
            ])
        lines.extend([
            "    security_opt:",
            '      - "no-new-privileges:true"',
            "    read_only: true",
            "    cap_drop:",
            '      - "ALL"',
            "    tmpfs:",
            "      - /tmp",
            "    env_file:",
            f'      - "config/env/.env.{mcp}"',
            "    networks:",
            "      - defenseclaw_net",
            "",
        ])
    lines.extend([
        "networks:",
        "  defenseclaw_net:",
        "    driver: bridge",
    ])
    return "\n".join(lines) + "\n"


def generate_docker_compose(selected_mcps: list[str], output_path: str | Path) -> str:
    """Writes hardened docker-compose.mcp.yml to output_path."""
    content = generate_docker_compose_string(selected_mcps)
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(content)
    return str(out_p)
