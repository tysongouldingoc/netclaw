"""Fixtures for MCP installer and DefenseClaw test suites."""

import json
import os
import pytest


@pytest.fixture
def mock_openclaw_home(tmp_path, monkeypatch):
    """Creates a temporary isolated OPENCLAW HOME directory structure."""
    home_dir = tmp_path / ".openclaw"
    home_dir.mkdir(parents=True, exist_ok=True)

    config_dir = home_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    env_dir = config_dir / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(env_dir, 0o700)
    except Exception:
        pass

    master_env = config_dir / ".env"
    master_env.write_text(
        "OPENAI_API_KEY=sk-proj-test123456789\n"
        "GITHUB_TOKEN=ghp_secret9876543210\n"
        "DATABASE_URL=postgres://user:pass@localhost:5432/db\n"
    )
    try:
        os.chmod(master_env, 0o600)
    except Exception:
        pass

    openclaw_json = config_dir / "openclaw.json"
    initial_config = {
        "version": "1.0",
        "mcpServers": {
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
            }
        },
    }
    openclaw_json.write_text(json.dumps(initial_config, indent=2))

    gait_dir = home_dir / "n2n" / "gait"
    gait_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("OPENCLAW_HOME", str(home_dir))
    monkeypatch.setenv("HOME", str(tmp_path))

    return {
        "root": tmp_path,
        "openclaw_home": home_dir,
        "config_dir": config_dir,
        "env_dir": env_dir,
        "master_env": master_env,
        "openclaw_json": openclaw_json,
        "gait_dir": gait_dir,
    }


@pytest.fixture
def mock_defenseclaw_proxy():
    """Mock configuration fixture for DefenseClaw proxy on port 4000."""
    return {
        "host": "127.0.0.1",
        "port": 4000,
        "health_endpoint": "http://127.0.0.1:4000/healthz",
        "expected_response": {"status": "ok", "service": "defenseclaw-proxy"},
        "timeout": 3.0,
    }
