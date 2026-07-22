"""Global pytest configuration and cross-platform stubs for NetClaw test suites."""

import os
import sys
import types
import pytest

# Ensure repository root and protocol-mcp are in sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

PROTOCOL_MCP = os.path.join(REPO_ROOT, "mcp-servers", "protocol-mcp")
if PROTOCOL_MCP not in sys.path:
    sys.path.insert(0, PROTOCOL_MCP)

# Inject synthetic fcntl stub for non-POSIX environments (Windows)
if "fcntl" not in sys.modules:
    try:
        import fcntl  # noqa: F401
    except ImportError:
        fcntl_mock = types.ModuleType("fcntl")
        fcntl_mock.LOCK_EX = 2
        fcntl_mock.LOCK_SH = 1
        fcntl_mock.LOCK_NB = 4
        fcntl_mock.LOCK_UN = 8

        def flock(fd, op):
            pass

        def ioctl(fd, request, *args, **kwargs):
            return 0

        fcntl_mock.flock = flock
        fcntl_mock.ioctl = ioctl
        sys.modules["fcntl"] = fcntl_mock

pytest_plugins = [
    "tests.fixtures.mcp_installer.conftest",
]
