"""Database layer for Portman - SQLite-based port registry."""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import platformdirs


@dataclass
class PortRange:
    """Port range for a service."""

    service: str
    start: int
    end: int


class Database:
    """SQLite database manager for port allocations."""

    _lock = threading.Lock()

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize database connection.

        Args:
            db_path: Path to the SQLite database file. If None, uses default location.
        """
        if db_path is None:
            data_dir = Path(platformdirs.user_data_dir("portman", "portman"))
            data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            db_path = data_dir / "registry.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Initialize database schema if not exists."""
        with self._lock, self._get_connection() as conn:
            # Check if schema is initialized
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            if cursor.fetchone() is None:
                # Create schema
                conn.executescript(
                    """
                    -- Version tracking
                    CREATE TABLE schema_version (
                        version INTEGER PRIMARY KEY
                    );
                    INSERT INTO schema_version VALUES (1);

                    -- Port allocations
                    CREATE TABLE allocations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        context_hash TEXT NOT NULL,
                        context_path TEXT NOT NULL,
                        context_label TEXT,
                        service TEXT NOT NULL,
                        port INTEGER NOT NULL UNIQUE,
                        container_port INTEGER,
                        env_var TEXT,
                        source TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        last_accessed_at TEXT DEFAULT (datetime('now')),
                        UNIQUE(context_hash, service)
                    );

                    CREATE INDEX idx_allocations_context ON allocations(context_hash);
                    CREATE INDEX idx_allocations_port ON allocations(port);
                    CREATE INDEX idx_allocations_last_accessed ON allocations(last_accessed_at);

                    -- Port ranges configuration
                    CREATE TABLE port_ranges (
                        service TEXT PRIMARY KEY,
                        range_start INTEGER NOT NULL,
                        range_end INTEGER NOT NULL
                    );

                    -- Default ranges
                    INSERT INTO port_ranges VALUES ('postgres', 5432, 5499);
                    INSERT INTO port_ranges VALUES ('postgresql', 5432, 5499);
                    INSERT INTO port_ranges VALUES ('mysql', 3306, 3399);
                    INSERT INTO port_ranges VALUES ('mariadb', 3306, 3399);
                    INSERT INTO port_ranges VALUES ('redis', 6379, 6449);
                    INSERT INTO port_ranges VALUES ('mongodb', 27017, 27099);
                    INSERT INTO port_ranges VALUES ('mongo', 27017, 27099);
                    INSERT INTO port_ranges VALUES ('elasticsearch', 9200, 9299);
                    INSERT INTO port_ranges VALUES ('meilisearch', 7700, 7799);
                    INSERT INTO port_ranges VALUES ('rabbitmq', 5672, 5699);
                    INSERT INTO port_ranges VALUES ('kafka', 9092, 9099);
                    INSERT INTO port_ranges VALUES ('default', 10000, 19999);
                """
                )
                conn.commit()

    def create_allocation(
        self,
        context_hash: str,
        context_path: str,
        context_label: str,
        service: str,
        port: int,
        container_port: int | None = None,
        env_var: str | None = None,
        source: str | None = None,
    ) -> int:
        """Create a new port allocation.

        Args:
            context_hash: Context hash identifier
            context_path: Absolute path to the project
            context_label: Human-readable label
            service: Service name
            port: Allocated port number
            container_port: Internal container port
            env_var: Environment variable name
            source: Source of the allocation

        Returns:
            ID of the created allocation

        Raises:
            sqlite3.IntegrityError: If port or context+service already allocated
        """
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO allocations (
                    context_hash, context_path, context_label, service, port,
                    container_port, env_var, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context_hash,
                    context_path,
                    context_label,
                    service,
                    port,
                    container_port,
                    env_var,
                    source,
                ),
            )
            conn.commit()
            assert cursor.lastrowid is not None, "Failed to create allocation"
            return cursor.lastrowid

    def get_allocation(self, context_hash: str, service: str) -> dict[str, Any] | None:
        """Get allocation for a context and service.

        Args:
            context_hash: Context hash
            service: Service name

        Returns:
            Allocation dict or None if not found
        """
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM allocations
                WHERE context_hash = ? AND service = ?
                """,
                (context_hash, service),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_allocations_by_context(self, context_hash: str) -> list[dict[str, Any]]:
        """Get all allocations for a context.

        Args:
            context_hash: Context hash

        Returns:
            List of allocation dicts
        """
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM allocations
                WHERE context_hash = ?
                ORDER BY service
                """,
                (context_hash,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_allocations(self) -> list[dict[str, Any]]:
        """Get all allocations.

        Returns:
            List of all allocation dicts
        """
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM allocations
                ORDER BY context_label, service
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_allocated_ports(self) -> set[int]:
        """Get set of all allocated ports.

        Returns:
            Set of port numbers
        """
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("SELECT port FROM allocations")
            return {row["port"] for row in cursor.fetchall()}

    def touch_allocation(self, allocation_id: int) -> None:
        """Update last_accessed_at timestamp.

        Args:
            allocation_id: Allocation ID to update
        """
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                UPDATE allocations
                SET last_accessed_at = datetime('now')
                WHERE id = ?
                """,
                (allocation_id,),
            )
            conn.commit()

    def delete_allocation(self, allocation_id: int) -> None:
        """Delete an allocation.

        Args:
            allocation_id: Allocation ID to delete
        """
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM allocations WHERE id = ?", (allocation_id,))
            conn.commit()

    def delete_allocations_by_context(self, context_hash: str) -> int:
        """Delete all allocations for a context.

        Args:
            context_hash: Context hash

        Returns:
            Number of deleted allocations
        """
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM allocations WHERE context_hash = ?", (context_hash,)
            )
            conn.commit()
            return cursor.rowcount

    def delete_allocation_by_service(self, context_hash: str, service: str) -> bool:
        """Delete allocation for a specific service in a context.

        Args:
            context_hash: Context hash
            service: Service name

        Returns:
            True if deleted, False if not found
        """
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM allocations WHERE context_hash = ? AND service = ?",
                (context_hash, service),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_stale_allocations(self, days: int = 30) -> list[dict[str, Any]]:
        """Get allocations not accessed in the last N days.

        Args:
            days: Number of days

        Returns:
            List of stale allocation dicts
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM allocations
                WHERE last_accessed_at < ?
                ORDER BY last_accessed_at
                """,
                (cutoff_date,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_port_range(self, service: str) -> PortRange:
        """Get port range for a service.

        Args:
            service: Service name

        Returns:
            PortRange object (returns 'default' range if service not found)
        """
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM port_ranges WHERE service = ?", (service,)
            )
            row = cursor.fetchone()

            if row is None:
                # Try to find default range
                cursor = conn.execute(
                    "SELECT * FROM port_ranges WHERE service = 'default'"
                )
                row = cursor.fetchone()

            if row is None:
                # Fallback hardcoded default
                return PortRange(service="default", start=10000, end=19999)

            return PortRange(
                service=row["service"], start=row["range_start"], end=row["range_end"]
            )

    def set_port_range(self, service: str, start: int, end: int) -> None:
        """Set or update port range for a service.

        Args:
            service: Service name
            start: Range start port
            end: Range end port
        """
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO port_ranges (service, range_start, range_end)
                VALUES (?, ?, ?)
                ON CONFLICT(service) DO UPDATE SET
                    range_start = excluded.range_start,
                    range_end = excluded.range_end
                """,
                (service, start, end),
            )
            conn.commit()

    def get_all_port_ranges(self) -> list[PortRange]:
        """Get all configured port ranges.

        Returns:
            List of PortRange objects
        """
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM port_ranges ORDER BY service"
            )
            return [
                PortRange(
                    service=row["service"],
                    start=row["range_start"],
                    end=row["range_end"],
                )
                for row in cursor.fetchall()
            ]
