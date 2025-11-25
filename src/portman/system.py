"""System port scanner for Portman."""

import re
import socket
import subprocess


class SystemScanner:
    """Scan system for ports in use."""

    def get_listening_ports(self) -> set[int]:
        """Get all TCP ports currently in LISTEN state.

        Tries multiple methods in order:
        1. ss (Linux, fast)
        2. lsof (macOS/Linux, slower)
        3. netstat (Windows/universal, slowest)

        Returns:
            Set of port numbers in use
        """
        ports: set[int] = set()

        # Try ss first (Linux, fastest)
        ports.update(self._scan_ss())

        # Fallback to lsof (macOS, universal)
        if not ports:
            ports.update(self._scan_lsof())

        # Final fallback to netstat (Windows, universal)
        if not ports:
            ports.update(self._scan_netstat())

        return ports

    def is_port_bindable(self, port: int) -> bool:
        """Test if a port can be bound to.

        Args:
            port: Port number to test

        Returns:
            True if port is available, False otherwise
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                return True
        except OSError:
            return False

    def _scan_ss(self) -> set[int]:
        """Scan ports using ss command (Linux).

        Returns:
            Set of listening ports
        """
        try:
            result = subprocess.run(
                ["ss", "-tlnH"],  # TCP, listening, numeric, no header
                capture_output=True,
                text=True,
                timeout=5,
            )
            ports = set()
            for line in result.stdout.splitlines():
                # Format: LISTEN 0 128 *:5432 *:*
                # or: LISTEN 0 128 127.0.0.1:5432 *:*
                match = re.search(r":(\d+)\s", line)
                if match:
                    ports.add(int(match.group(1)))
            return ports
        except (subprocess.SubprocessError, FileNotFoundError):
            return set()

    def _scan_lsof(self) -> set[int]:
        """Scan ports using lsof command (macOS/Linux).

        Returns:
            Set of listening ports
        """
        try:
            result = subprocess.run(
                ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ports = set()
            for line in result.stdout.splitlines()[1:]:  # Skip header
                # Format: COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME
                # NAME is like: *:5432 (LISTEN)
                match = re.search(r":(\d+)\s", line)
                if match:
                    ports.add(int(match.group(1)))
            return ports
        except (subprocess.SubprocessError, FileNotFoundError):
            return set()

    def _scan_netstat(self) -> set[int]:
        """Scan ports using netstat command (Windows/universal).

        Returns:
            Set of listening ports
        """
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
                    # Extract port from address:port format
                    match = re.search(r":(\d+)\s", line)
                    if match:
                        ports.add(int(match.group(1)))
            return ports
        except (subprocess.SubprocessError, FileNotFoundError):
            return set()
