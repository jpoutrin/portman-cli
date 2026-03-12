"""Tests for system helpers."""

import json
import subprocess

from portman.system import DockerInspector


class CompletedProcess:
    """Small stand-in for subprocess results."""

    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


def test_docker_inspector_unavailable(monkeypatch):
    """Test Docker inspector handles missing Docker CLI."""

    def fake_run(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)

    inspector = DockerInspector()
    assert inspector.is_docker_available() is False
    assert inspector.list_volumes() == set()
    assert inspector.inspect_volume("missing") is None
    assert inspector.remove_volume("missing") is False


def test_docker_inspector_inspects_and_removes(monkeypatch):
    """Test Docker volume inspection and deletion."""

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[:3] == ["docker", "info", "--format"]:
            return CompletedProcess(0, "{}")
        if cmd[:4] == ["docker", "volume", "ls", "--format"]:
            return CompletedProcess(0, "vol1\nvol2\n")
        if cmd[:3] == ["docker", "volume", "inspect"]:
            return CompletedProcess(0, json.dumps([{"Name": cmd[3]}]))
        if cmd[:3] == ["docker", "volume", "rm"]:
            return CompletedProcess(0, cmd[3])
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    inspector = DockerInspector()
    assert inspector.is_docker_available() is True
    assert inspector.list_volumes() == {"vol1", "vol2"}
    assert inspector.inspect_volume("vol1") == {"Name": "vol1"}
    assert inspector.remove_volume("vol1") is True
