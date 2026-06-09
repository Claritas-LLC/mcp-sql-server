"""Regression tests for container dependency imports.

These tests verify that critical runtime imports resolve correctly
and that no ModuleNotFoundError occurs for packaging or FastMCP.
"""
import subprocess
import sys
from pathlib import Path

import pytest


def test_packaging_import() -> None:
    """packaging must be importable (transitive dependency of FastMCP)."""
    import packaging  # noqa: F401


def test_fastmcp_import() -> None:
    """FastMCP must be importable (core server dependency)."""
    from fastmcp import FastMCP  # noqa: F401


def test_packaging_fastmcp_import_container() -> None:
    """Verify packaging and FastMCP import inside the Docker container."""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "harryvaldez/mcp-sql-server:latest",
            "-c",
            "import packaging; from fastmcp import FastMCP; print('ok')",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"Container import probe failed:\n"
        f"  stdout: {result.stdout}\n"
        f"  stderr: {result.stderr}"
    )
    assert result.stdout.strip() == "ok"
