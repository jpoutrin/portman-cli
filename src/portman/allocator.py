"""Port allocation logic for Portman."""

from .db import Database
from .system import SystemScanner


class PortAllocationError(Exception):
    """Raised when no port can be allocated."""

    pass


class PortAllocator:
    """Allocate ports with machine-wide uniqueness guarantee."""

    def __init__(self, db: Database) -> None:
        """Initialize allocator.

        Args:
            db: Database instance
        """
        self.db = db
        self.system = SystemScanner()

    def allocate(
        self,
        service: str,
        context_hash: str,
        preferred_port: int | None = None,
    ) -> int:
        """Allocate a port for a service in a context.

        Strategy:
        1. If already allocated for this context+service → return existing port
        2. If preferred_port specified and available → use it
        3. Otherwise → find first free port in service range
        4. If service range exhausted → try default range

        Args:
            service: Service name (e.g., "postgres", "redis")
            context_hash: Context hash identifier
            preferred_port: Preferred port number (optional)

        Returns:
            The allocated port number

        Raises:
            PortAllocationError: If no port is available
        """
        # 1. Check if already allocated
        existing = self.db.get_allocation(context_hash, service)
        if existing:
            # Update last accessed timestamp
            self.db.touch_allocation(existing["id"])
            return existing["port"]

        # 2. Collect unavailable ports
        unavailable = self._get_unavailable_ports()

        # 3. Try preferred port
        if preferred_port and self._is_port_available(preferred_port, unavailable):
            return preferred_port

        # 4. Find port in service range
        port_range = self.db.get_port_range(service)

        for port in range(port_range.start, port_range.end + 1):
            if self._is_port_available(port, unavailable):
                return port

        # 5. Fallback to default range if not already trying it
        if service != "default":
            default_range = self.db.get_port_range("default")
            for port in range(default_range.start, default_range.end + 1):
                if self._is_port_available(port, unavailable):
                    return port

        raise PortAllocationError(
            f"No available port for service '{service}' "
            f"(tried range {port_range.start}-{port_range.end})"
        )

    def _get_unavailable_ports(self) -> set[int]:
        """Get set of all unavailable ports.

        Combines:
        - Ports allocated in database
        - Ports currently listening on system

        Returns:
            Set of unavailable port numbers
        """
        db_ports = self.db.get_all_allocated_ports()
        system_ports = self.system.get_listening_ports()
        return db_ports | system_ports

    def _is_port_available(self, port: int, unavailable: set[int]) -> bool:
        """Check if a port is available.

        Args:
            port: Port number to check
            unavailable: Set of known unavailable ports

        Returns:
            True if port is available, False otherwise
        """
        if port in unavailable:
            return False
        return self.system.is_port_bindable(port)
