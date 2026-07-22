"""N2N Integration tests for Selective MCP Installer CLI & Secret Slicing (Feature 057)."""

import importlib.util
import json
import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _import_mcp_installer():
    """Helper to dynamically import scripts/mcp-installer.py."""
    path = os.path.join(REPO_ROOT, "scripts", "mcp-installer.py")
    if not os.path.exists(path):
        raise ModuleNotFoundError(f"Product script not found: {path}")
    spec = importlib.util.spec_from_file_location("mcp_installer", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mcp_installer"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_installer_server_discovery_and_selection(mock_openclaw_home):
    """Asserts CLI discovery under mcp-servers/*/ and --select / --all parsing."""
    installer = _import_mcp_installer()
    
    servers = installer.discover_mcp_servers()
    assert isinstance(servers, dict)
    assert len(servers) > 0

    selected = installer.filter_servers(servers, select=["github"])
    assert "github" in selected
    assert len(selected) == 1


def test_openclaw_json_registration_update(mock_openclaw_home):
    """Asserts atomic update of openclaw.json mcpServers object with backup creation."""
    installer = _import_mcp_installer()
    
    config_file = mock_openclaw_home["openclaw_json"]
    backup_file = config_file.with_name("openclaw.json.bak")

    installer.register_server(
        name="sqlite",
        config={
            "command": "uvx",
            "args": ["mcp-server-sqlite", "--db-path", "/tmp/test.db"],
        },
    )

    assert backup_file.exists(), "openclaw.json.bak must be created before mutation"

    with open(config_file) as f:
        data = json.load(f)
    assert "sqlite" in data.get("mcpServers", {})


def test_secret_slicing_and_permission_0600(mock_openclaw_home):
    """Asserts secret slicing into .env.<mcp> with 0600 file and 0700 dir permissions."""
    installer = _import_mcp_installer()
    
    sliced_path = installer.slice_secrets_for_mcp(
        mcp_name="github",
        required_keys=["GITHUB_TOKEN"],
    )

    assert os.path.exists(sliced_path)
    assert os.path.basename(sliced_path) == ".env.github"
    
    # Check parent dir permissions (0700)
    env_dir = os.path.dirname(sliced_path)
    dir_mode = oct(os.stat(env_dir).st_mode & 0o777)
    assert dir_mode in ("0o700", "0700"), f"Parent dir mode should be 0700, got {dir_mode}"

    # Check file contents and permissions (0600)
    with open(sliced_path) as f:
        content = f.read()
    assert "GITHUB_TOKEN=ghp_secret9876543210" in content
    assert "OPENAI_API_KEY" not in content, "Unrequested credentials must be excluded"
    
    file_mode = oct(os.stat(sliced_path).st_mode & 0o777)
    assert file_mode in ("0o600", "0600"), f"File mode should be 0600, got {file_mode}"


def test_non_interactive_tty_fallback(mock_openclaw_home, monkeypatch):
    """Asserts unattended execution without --select or --all fails fast with exit code 1."""
    installer = _import_mcp_installer()
    
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    
    with pytest.raises(SystemExit) as exc_info:
        installer.main(args=[])
    
    assert exc_info.value.code == 1


def test_docker_compose_config_syntax(mock_openclaw_home):
    """Validates generated docker-compose.mcp.yml structure."""
    path = os.path.join(REPO_ROOT, "scripts", "lib", "mcp_compose.py")
    if not os.path.exists(path):
        raise ModuleNotFoundError(f"Product script not found: {path}")
    spec = importlib.util.spec_from_file_location("mcp_compose", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mcp_compose"] = mod
    spec.loader.exec_module(mod)

    out_file = str(mock_openclaw_home["config_dir"] / "docker-compose.mcp.yml")
    mod.generate_docker_compose(selected_mcps=["github"], output_path=out_file)
    
    assert os.path.exists(out_file)
    with open(out_file) as f:
        content = f.read()
    assert "services:" in content
    assert "no-new-privileges:true" in content


def test_systemd_unit_syntax(mock_openclaw_home):
    """Validates generated systemd user unit text."""
    path = os.path.join(REPO_ROOT, "scripts", "in2n-services.py")
    spec = importlib.util.spec_from_file_location("in2n_services", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    unit_text = mod._mcp_unit_text(mcp_name="github")
    assert "[Unit]" in unit_text
    assert "[Service]" in unit_text
    assert "NoNewPrivileges=yes" in unit_text
    assert "ProtectSystem=strict" in unit_text


def test_gait_audit_logging_e2e(mock_openclaw_home):
    """Asserts installer appends an immutable audit commit to GAIT repo on install."""
    installer = _import_mcp_installer()
    
    result = installer.log_gait_event(
        event_type="MCP_INSTALL",
        details={"server": "github", "status": "installed"},
    )
    assert result.get("logged") is True
    assert result.get("commit_sha") is not None


def test_status_option_without_module_error(mock_openclaw_home, monkeypatch):
    """Asserts --status imports bgp.federation.posture without ModuleNotFoundError."""
    installer = _import_mcp_installer()
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    
    with pytest.raises(SystemExit) as exc_info:
        installer.main(args=["--status"])
    assert exc_info.value.code == 0


def test_batch_installer_transactional_rollback(mock_openclaw_home, monkeypatch):
    """Asserts batch installer failure restores openclaw.json, purges created .env.<mcp> secret files, and logs GAIT event."""
    installer = _import_mcp_installer()
    config_file = mock_openclaw_home["openclaw_json"]
    
    initial_content = json.dumps({"version": "1.0", "mcpServers": {"existing": {"command": "echo"}}})
    config_file.write_text(initial_content)
    
    original_slice = installer.slice_secrets_for_mcp
    call_count = [0]
    
    def failing_slice(mcp_name, keys):
        call_count[0] += 1
        res = original_slice(mcp_name, keys)
        if call_count[0] > 1:
            raise RuntimeError("Simulated secret slicing failure on second server")
        return res

    monkeypatch.setattr(installer, "slice_secrets_for_mcp", failing_slice)

    with pytest.raises(RuntimeError, match="Simulated secret slicing failure"):
        installer.main(args=["--select", "github,sqlite"])

    # openclaw.json should be restored to initial state
    assert config_file.read_text() == initial_content

    # Partial secret files (.env.github, .env.sqlite) should be purged
    env_dir = mock_openclaw_home["config_dir"] / "env"
    assert not (env_dir / ".env.github").exists()
    assert not (env_dir / ".env.sqlite").exists()

    # GAIT audit log should contain INSTALLATION_TRANSACTION_ROLLED_BACK
    audit_file = mock_openclaw_home["gait_dir"] / "audit.log"
    assert audit_file.exists()
    audit_text = audit_file.read_text()
    assert "INSTALLATION_TRANSACTION_ROLLED_BACK" in audit_text


