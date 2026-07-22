"""N2N Security Gate & Fail-Closed Model Guard Tests (Feature 057)."""

import importlib.util
import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _import_register_script():
    path = os.path.join(REPO_ROOT, "scripts", "register-mcps-with-defenseclaw.py")
    spec = importlib.util.spec_from_file_location("register_mcps", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_proxy_unreachable_failclosed_in_production(mock_openclaw_home, monkeypatch):
    """Under production mode, unreachable proxy port 4000 halts setup with exit code 1."""
    register_script = _import_register_script()
    
    monkeypatch.setenv("N2N_RISK_MODE", "production")
    
    # Ensure proxy health check function exists and fails when proxy is down
    assert hasattr(register_script, "verify_model_guard_proxy"), (
        "register-mcps-with-defenseclaw.py must implement verify_model_guard_proxy(port=4000)"
    )

    with pytest.raises(SystemExit) as exc_info:
        register_script.verify_model_guard_proxy(port=4000, timeout=3.0)

    assert exc_info.value.code == 1


def test_static_scan_high_risk_finding_abort(mock_openclaw_home, monkeypatch):
    """Pre-activation static scan with HIGH/CRITICAL finding aborts registration in production."""
    register_script = _import_register_script()
    
    monkeypatch.setenv("N2N_RISK_MODE", "production")
    assert hasattr(register_script, "run_static_security_scan"), (
        "register-mcps-with-defenseclaw.py must implement run_static_security_scan(mcp_name)"
    )

    result = register_script.run_static_security_scan(
        mcp_name="malicious-mcp",
        source_dir="/tmp/fake-mcp",
        mock_findings=[{"severity": "HIGH", "rule": "UNAUTHORIZED_EXEC"}],
    )
    assert result["passed"] is False
    assert result["aborted"] is True
    assert result["status"] == "QUARANTINED"


def test_proxy_and_scan_bypass_in_testing_mode(mock_openclaw_home, monkeypatch):
    """Under testing mode, proxy/scan failures generate warnings but permit non-blocking exit 0."""
    register_script = _import_register_script()
    
    monkeypatch.setenv("N2N_RISK_MODE", "testing")

    res = register_script.verify_model_guard_proxy(port=4000, timeout=3.0)
    assert res["status"] == "WARNING_BYPASS"
    assert res["exit_code"] == 0


def test_proxy_socket_timeout_handling(mock_openclaw_home, monkeypatch):
    """Asserts proxy probe strictly enforces 3.0 second timeout before triggering fail-closed abort."""
    register_script = _import_register_script()
    
    monkeypatch.setenv("N2N_RISK_MODE", "production")
    
    # Probe a hanging port with 3.0s timeout
    res = register_script.probe_proxy_endpoint(
        url="http://10.255.255.1:4000/healthz",
        timeout=3.0,
    )
    assert res["timed_out"] is True
    assert res["elapsed_seconds"] <= 3.5
    assert res["fail_closed"] is True


def test_proxy_json_payload_validation(mock_openclaw_home, monkeypatch):
    """Asserts verify_model_guard_proxy requires status=='ok' and service=='defenseclaw-proxy' in HTTP response."""
    import io
    import json
    import urllib.request

    register_script = _import_register_script()
    monkeypatch.setenv("N2N_RISK_MODE", "production")

    class MockHTTPResponse:
        def __init__(self, status, data):
            self.status = status
            self._data = json.dumps(data).encode("utf-8")

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    # Valid response -> OK
    valid_resp = MockHTTPResponse(200, {"status": "ok", "service": "defenseclaw-proxy"})
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=3.0: valid_resp)
    res = register_script.verify_model_guard_proxy(port=4000)
    assert res["healthy"] is True

    # Invalid status payload -> Fail closed in production
    invalid_payload_resp = MockHTTPResponse(200, {"status": "error", "service": "defenseclaw-proxy"})
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=3.0: invalid_payload_resp)
    with pytest.raises(SystemExit) as exc_info:
        register_script.verify_model_guard_proxy(port=4000)
    assert exc_info.value.code == 1

    # Invalid service payload -> Fail closed in production
    invalid_service_resp = MockHTTPResponse(200, {"status": "ok", "service": "other-service"})
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=3.0: invalid_service_resp)
    with pytest.raises(SystemExit) as exc_info:
        register_script.verify_model_guard_proxy(port=4000)
    assert exc_info.value.code == 1

