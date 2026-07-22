"""N2N Dual-Target Posture Evaluation & WSL2 Degradation Tests (Feature 057)."""

import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "mcp-servers", "protocol-mcp"))


def _get_posture_evaluator():
    from bgp.federation.posture import MCPPostureEvaluator
    return MCPPostureEvaluator()


def test_posture_all_controls_enforced(mock_openclaw_home):
    """Asserts posture engine returns 'production — enforced' when all security controls pass."""
    evaluator = _get_posture_evaluator()
    
    status = evaluator.evaluate_posture(
        target="docker-compose",
        risk_mode="production",
        mock_controls={
            "proxy_health": True,
            "secret_isolation": True,
            "confinement_directives": True,
            "kernel_support": True,
        },
    )
    assert status["verdict"] == "production — enforced"
    assert status["degraded"] is False


@pytest.mark.parametrize(
    "missing_control,expected_reason",
    [
        ("proxy_health", "production — DEGRADED (model_guard_proxy_offline)"),
        ("secret_isolation", "production — DEGRADED (master_env_permission_leak)"),
        ("confinement_directives", "production — DEGRADED (missing_confinement_directives)"),
    ],
)
def test_posture_degraded_on_missing_control(mock_openclaw_home, missing_control, expected_reason):
    """Parametrized assertion that missing control degrades posture to expected DEGRADED reason."""
    evaluator = _get_posture_evaluator()
    
    controls = {
        "proxy_health": True,
        "secret_isolation": True,
        "confinement_directives": True,
        "kernel_support": True,
    }
    controls[missing_control] = False

    status = evaluator.evaluate_posture(
        target="docker-compose",
        risk_mode="production",
        mock_controls=controls,
    )
    assert status["verdict"] == expected_reason
    assert status["degraded"] is True


def test_wsl2_kernel_limitation_posture_degradation(mock_openclaw_home, monkeypatch):
    """Asserts systemd target under WSL2 kernel limits degrades to WSL2_kernel_limitation."""
    evaluator = _get_posture_evaluator()
    
    # Simulate WSL2 kernel environment
    monkeypatch.setattr(evaluator, "is_wsl2_environment", lambda: True)

    status = evaluator.evaluate_posture(
        target="systemd",
        risk_mode="production",
        mock_controls={
            "proxy_health": True,
            "secret_isolation": True,
            "confinement_directives": True,
            "kernel_support": False,
        },
    )
    assert status["verdict"] == "production — DEGRADED (WSL2_kernel_limitation)"
    assert status["wsl2_degraded"] is True


def test_target_specific_posture_evaluation(mock_openclaw_home, monkeypatch):
    """Asserts posture engine detects missing Docker daemon or inaccessible systemd user bus."""
    evaluator = _get_posture_evaluator()

    monkeypatch.setattr(evaluator, "check_docker_daemon_available", lambda: False)
    compose_status = evaluator.evaluate_target_availability(target="docker-compose")
    assert compose_status["available"] is False
    assert compose_status["reason"] == "docker_daemon_unreachable"

    monkeypatch.setattr(evaluator, "check_systemd_user_bus_available", lambda: False)
    systemd_status = evaluator.evaluate_target_availability(target="systemd")
    assert systemd_status["available"] is False
    assert systemd_status["reason"] == "systemd_user_bus_unreachable"
