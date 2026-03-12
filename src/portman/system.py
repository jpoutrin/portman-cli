"""System scanners for Portman."""

import json
import re
import socket
import subprocess


class SystemScanner:
    """Scan system for ports in use."""

    def get_listening_ports(self) -> set[int]:
        """Get all TCP ports currently in LISTEN state."""
        ports: set[int] = set()
        ports.update(self._scan_ss())
        if not ports:
            ports.update(self._scan_lsof())
        if not ports:
            ports.update(self._scan_netstat())
        return ports

    def is_port_bindable(self, port: int) -> bool:
        """Test if a port can be bound to."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
                return True
        except OSError:
            return False

    def _scan_ss(self) -> set[int]:
        """Scan ports using ss command (Linux)."""
        try:
            result = subprocess.run(
                ["ss", "-tlnH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ports = set()
            for line in result.stdout.splitlines():
                match = re.search(r":(\d+)\s", line)
                if match:
                    ports.add(int(match.group(1)))
            return ports
        except (subprocess.SubprocessError, FileNotFoundError):
            return set()

    def _scan_lsof(self) -> set[int]:
        """Scan ports using lsof command (macOS/Linux)."""
        try:
            result = subprocess.run(
                ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ports = set()
            for line in result.stdout.splitlines()[1:]:
                match = re.search(r":(\d+)\s", line)
                if match:
                    ports.add(int(match.group(1)))
            return ports
        except (subprocess.SubprocessError, FileNotFoundError):
            return set()

    def _scan_netstat(self) -> set[int]:
        """Scan ports using netstat command (Windows/universal)."""
        try:
            result = subprocess.run(
                ["netstat", "-tln"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ports = set()
            for line in result.stdout.splitlines():
                if "LISTEN" in line:
                    match = re.search(r":(\d+)\s", line)
                    if match:
                        ports.add(int(match.group(1)))
            return ports
        except (subprocess.SubprocessError, FileNotFoundError):
            return set()


class DockerInspector:
    """Inspect Docker volumes with graceful fallbacks."""

    def is_docker_available(self) -> bool:
        """Return True if Docker CLI and daemon are reachable."""
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def list_volumes(self) -> set[str]:
        """Return the set of Docker volume names."""
        try:
            result = subprocess.run(
                ["docker", "volume", "ls", "--format", "{{.Name}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return set()

        if result.returncode != 0:
            return set()

        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def inspect_volume(self, name: str) -> dict | None:
        """Inspect a Docker volume by name."""
        try:
            result = subprocess.run(
                ["docker", "volume", "inspect", name],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return None

        if result.returncode != 0:
            return None

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, list) or not payload:
            return None

        volume = payload[0]
        return volume if isinstance(volume, dict) else None

    def remove_volume(self, name: str) -> bool:
        """Delete a Docker volume by name."""
        try:
            result = subprocess.run(
                ["docker", "volume", "rm", name],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

        return result.returncode == 0
