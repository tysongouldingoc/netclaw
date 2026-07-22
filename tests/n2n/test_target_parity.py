"""N2N Confinement Equivalence & Dual Target Parity Tests (Feature 057)."""

import importlib.util
import json
import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _import_in2n_services():
    path = os.path.join(REPO_ROOT, "scripts", "in2n-services.py")
    spec = importlib.util.spec_from_file_location("in2n_services", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_mcp_compose():
    path = os.path.join(REPO_ROOT, "scripts", "lib", "mcp_compose.py")
    if not os.path.exists(path):
        raise ModuleNotFoundError(f"Product script not found: {path}")
    spec = importlib.util.spec_from_file_location("mcp_compose", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_confinement_directive_parity(mock_openclaw_home):
    """Asserts 1:1 structural equivalence of security confinement between targets."""
    in2n = _import_in2n_services()
    compose = _import_mcp_compose()

    # Systemd confinement directives
    unit_text = in2n._mcp_unit_text("github")
    assert "NoNewPrivileges=yes" in unit_text
    assert "ProtectSystem=strict" in unit_text
    assert "PrivateTmp=yes" in unit_text
    assert "InaccessiblePaths=-%h/.openclaw/.env" in unit_text

    # Docker Compose confinement directives
    compose_yaml = compose.generate_docker_compose_string(["github"])
    assert "no-new-privileges:true" in compose_yaml
    assert "read_only: true" in compose_yaml
    assert 'cap_drop:\n      - "ALL"' in compose_yaml or 'cap_drop:\n      - ALL' in compose_yaml or 'cap_drop: ["ALL"]' in compose_yaml
    assert "tmpfs:\n      - /tmp" in compose_yaml or 'tmpfs: ["/tmp"]' in compose_yaml


def test_env_mount_isolation_parity(mock_openclaw_home):
    """Asserts both targets reference only isolated .env.<mcp> files, hiding master .env."""
    in2n = _import_in2n_services()
    compose = _import_mcp_compose()

    unit_text = in2n._mcp_unit_text("github")
    assert "EnvironmentFile=%h/.openclaw/config/env/.env.github" in unit_text
    assert "%h/.openclaw/config/.env" not in unit_text or "InaccessiblePaths=-%h/.openclaw/.env" in unit_text

    compose_dict = compose.get_service_dict("github")
    env_file = compose_dict.get("env_file", [])
    assert any(".env.github" in item for item in env_file)
    assert not any(item.endswith("config/.env") for item in env_file)


def test_single_source_of_truth_parity(mock_openclaw_home):
    """Asserts both target generators produce matching service sets derived from openclaw.json."""
    in2n = _import_in2n_services()
    compose = _import_mcp_compose()

    # Add 2 servers to openclaw.json
    config_file = mock_openclaw_home["openclaw_json"]
    config_data = {
        "mcpServers": {
            "github": {"command": "npx", "args": ["@modelcontextprotocol/server-github"]},
            "sqlite": {"command": "uvx", "args": ["mcp-server-sqlite"]},
        }
    }
    config_file.write_text(json.dumps(config_data))

    systemd_services = in2n.get_active_mcp_service_names()
    compose_services = compose.get_active_mcp_service_names()

    assert set(systemd_services) == {"github", "sqlite"}
    assert set(compose_services) == {"github", "sqlite"}
