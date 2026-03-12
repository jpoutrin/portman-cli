"""Database layer for Portman - SQLite-based registry."""

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import platformdirs


SCHEMA_VERSION = 2


@dataclass
class PortRange:
    """Port range for a service."""

    service: str
    start: int
    end: int


class Database:
    """SQLite database manager for allocations and tracked volumes."""

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
        """Initialize or migrate the database schema."""
        with self._lock, self._get_connection() as conn:
            current_version = self._get_schema_version(conn)
            if current_version == 0:
                self._create_schema_v1(conn)
                current_version = 1

            if current_version < 2:
                self._migrate_to_v2(conn)
                current_version = 2

            self._set_schema_version(conn, current_version)
            conn.commit()

    def _get_schema_version(self, conn: sqlite3.Connection) -> int:
        """Return the current schema version or 0 if uninitialized."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        if cursor.fetchone() is None:
            return 0

        cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
        return int(row["version"]) if row else 0

    def _set_schema_version(self, conn: sqlite3.Connection, version: int) -> None:
        """Persist the latest schema version."""
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    def _create_schema_v1(self, conn: sqlite3.Connection) -> None:
        """Create the original schema."""
        conn.executescript(
            """
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY
            );

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

            CREATE TABLE port_ranges (
                service TEXT PRIMARY KEY,
                range_start INTEGER NOT NULL,
                range_end INTEGER NOT NULL
            );

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

    def _migrate_to_v2(self, conn: sqlite3.Connection) -> None:
        """Add tracked volume support."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracked_volumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_hash TEXT NOT NULL,
                context_path TEXT NOT NULL,
                context_label TEXT,
                service TEXT NOT NULL DEFAULT '',
                compose_file TEXT NOT NULL,
                compose_volume_key TEXT NOT NULL,
                docker_volume_name TEXT NOT NULL,
                source_mount TEXT NOT NULL,
                owner TEXT NOT NULL DEFAULT 'portman',
                ownership_token TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                last_accessed_at TEXT DEFAULT (datetime('now')),
                UNIQUE(context_hash, compose_file, compose_volume_key, service)
            );

            CREATE INDEX IF NOT EXISTS idx_tracked_volumes_context
                ON tracked_volumes(context_hash);
            CREATE INDEX IF NOT EXISTS idx_tracked_volumes_name
                ON tracked_volumes(docker_volume_name);
            CREATE INDEX IF NOT EXISTS idx_tracked_volumes_last_accessed
                ON tracked_volumes(last_accessed_at);
            """
        )

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
        """Create a new port allocation."""
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
        """Get allocation for a context and service."""
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
        """Get all allocations for a context."""
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
        """Get all allocations."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM allocations
                ORDER BY context_label, service
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_allocated_ports(self) -> set[int]:
        """Get set of all allocated ports."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("SELECT port FROM allocations")
            return {row["port"] for row in cursor.fetchall()}

    def touch_allocation(self, allocation_id: int) -> None:
        """Update allocation access timestamp."""
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
        """Delete an allocation."""
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM allocations WHERE id = ?", (allocation_id,))
            conn.commit()

    def delete_allocations_by_context(self, context_hash: str) -> int:
        """Delete all allocations for a context."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM allocations WHERE context_hash = ?", (context_hash,))
            conn.commit()
            return cursor.rowcount

    def delete_allocation_by_service(self, context_hash: str, service: str) -> bool:
        """Delete allocation for a specific service in a context."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM allocations WHERE context_hash = ? AND service = ?",
                (context_hash, service),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_stale_allocations(self, days: int = 30) -> list[dict[str, Any]]:
        """Get allocations not accessed in the last N days."""
        modifier = f"-{days} days"
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM allocations
                WHERE last_accessed_at < datetime('now', ?)
                ORDER BY last_accessed_at
                """,
                (modifier,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def create_tracked_volume(
        self,
        *,
        context_hash: str,
        context_path: str,
        context_label: str,
        service: str | None,
        compose_file: str,
        compose_volume_key: str,
        docker_volume_name: str,
        source_mount: str,
        owner: str,
        ownership_token: str,
    ) -> int:
        """Create a tracked volume record."""
        normalized_service = service or ""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tracked_volumes (
                    context_hash, context_path, context_label, service, compose_file,
                    compose_volume_key, docker_volume_name, source_mount, owner,
                    ownership_token
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context_hash,
                    context_path,
                    context_label,
                    normalized_service,
                    compose_file,
                    compose_volume_key,
                    docker_volume_name,
                    source_mount,
                    owner,
                    ownership_token,
                ),
            )
            conn.commit()
            assert cursor.lastrowid is not None, "Failed to create tracked volume"
            return cursor.lastrowid

    def upsert_tracked_volume(
        self,
        *,
        context_hash: str,
        context_path: str,
        context_label: str,
        service: str | None,
        compose_file: str,
        compose_volume_key: str,
        docker_volume_name: str,
        source_mount: str,
        owner: str,
        ownership_token: str,
    ) -> int:
        """Create or refresh a tracked volume record."""
        normalized_service = service or ""
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tracked_volumes (
                    context_hash, context_path, context_label, service, compose_file,
                    compose_volume_key, docker_volume_name, source_mount, owner,
                    ownership_token
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(context_hash, compose_file, compose_volume_key, service)
                DO UPDATE SET
                    context_path = excluded.context_path,
                    context_label = excluded.context_label,
                    docker_volume_name = excluded.docker_volume_name,
                    source_mount = excluded.source_mount,
                    owner = excluded.owner,
                    ownership_token = excluded.ownership_token,
                    last_accessed_at = datetime('now')
                """,
                (
                    context_hash,
                    context_path,
                    context_label,
                    normalized_service,
                    compose_file,
                    compose_volume_key,
                    docker_volume_name,
                    source_mount,
                    owner,
                    ownership_token,
                ),
            )
            cursor = conn.execute(
                """
                SELECT id FROM tracked_volumes
                WHERE context_hash = ? AND compose_file = ? AND compose_volume_key = ?
                  AND service = ?
                """,
                (context_hash, compose_file, compose_volume_key, normalized_service),
            )
            row = cursor.fetchone()
            conn.commit()
            assert row is not None, "Failed to upsert tracked volume"
            return int(row["id"])

    def get_tracked_volumes_by_context(self, context_hash: str) -> list[dict[str, Any]]:
        """Get tracked volumes for a context."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM tracked_volumes
                WHERE context_hash = ?
                ORDER BY compose_volume_key, service
                """,
                (context_hash,),
            )
            return [self._normalize_tracked_volume_row(row) for row in cursor.fetchall()]

    def get_all_tracked_volumes(self) -> list[dict[str, Any]]:
        """Get all tracked volumes."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM tracked_volumes
                ORDER BY context_label, compose_volume_key, service
                """
            )
            return [self._normalize_tracked_volume_row(row) for row in cursor.fetchall()]

    def touch_tracked_volume(self, tracked_volume_id: int) -> None:
        """Update tracked volume access timestamp."""
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                UPDATE tracked_volumes
                SET last_accessed_at = datetime('now')
                WHERE id = ?
                """,
                (tracked_volume_id,),
            )
            conn.commit()

    def delete_tracked_volume(self, tracked_volume_id: int) -> None:
        """Delete a tracked volume record."""
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM tracked_volumes WHERE id = ?", (tracked_volume_id,))
            conn.commit()

    def delete_tracked_volumes_by_context(self, context_hash: str) -> int:
        """Delete all tracked volume rows for a context."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM tracked_volumes WHERE context_hash = ?",
                (context_hash,),
            )
            conn.commit()
            return cursor.rowcount

    def get_stale_tracked_volumes(self, days: int = 30) -> list[dict[str, Any]]:
        """Get tracked volumes not accessed in the last N days."""
        modifier = f"-{days} days"
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM tracked_volumes
                WHERE last_accessed_at < datetime('now', ?)
                ORDER BY last_accessed_at
                """,
                (modifier,),
            )
            return [self._normalize_tracked_volume_row(row) for row in cursor.fetchall()]

    def get_port_range(self, service: str) -> PortRange:
        """Get port range for a service."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM port_ranges WHERE service = ?", (service,))
            row = cursor.fetchone()

            if row is None:
                cursor = conn.execute("SELECT * FROM port_ranges WHERE service = 'default'")
                row = cursor.fetchone()

            if row is None:
                return PortRange(service="default", start=10000, end=19999)

            return PortRange(service=row["service"], start=row["range_start"], end=row["range_end"])

    def set_port_range(self, service: str, start: int, end: int) -> None:
        """Set or update port range for a service."""
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
        """Get all configured port ranges."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM port_ranges ORDER BY service")
            return [
                PortRange(
                    service=row["service"],
                    start=row["range_start"],
                    end=row["range_end"],
                )
                for row in cursor.fetchall()
            ]

    def _normalize_tracked_volume_row(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a tracked volume row to a dict with empty service normalized to None."""
        result = dict(row)
        result["service"] = result["service"] or None
        return result
