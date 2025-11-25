# Portman

**Port Manager for Development Environments**

Portman automatically manages port allocations across multiple git worktrees and development contexts, preventing port conflicts when running Docker services.

## The Problem

When working on multiple branches or worktrees of the same project, Docker services (PostgreSQL, Redis, etc.) conflict on ports. You end up manually managing port assignments, which is error-prone and time-consuming.

**Example:** Running PostgreSQL on port 5432 in worktree A crashes when you start the same service in worktree B.

## The Solution

Portman provides:

- **Automatic port allocation** - Each worktree gets unique ports
- **Machine-wide uniqueness** - No conflicts across any projects
- **Context-aware** - Automatically detects your project and branch
- **direnv integration** - Ports are automatically available as environment variables
- **Docker Compose discovery** - Auto-detects services from `docker-compose.yml`
- **Zero configuration** - Works out of the box

## Installation

### Using uv (recommended)

```bash
uv tool install portman-cli
```

### Using pip

```bash
pip install portman-cli
```

### From source

```bash
git clone https://github.com/jpoutrin/portman-cli.git
cd portman-cli
uv pip install -e .
```

## Quick Start

### 1. Basic Usage

Book a port for a service in your current worktree:

```bash
portman book postgres
```

Get the allocated port:

```bash
portman get postgres
# Output: 5432
```

### 2. Auto-discovery from docker-compose.yml

If you have a `docker-compose.yml` file, Portman can automatically discover and book ports for all services:

```bash
portman book --auto
```

This scans your `docker-compose.yml` and allocates ports for each service.

For custom compose file names:

```bash
portman book --auto --compose-file docker-compose.prod.yml
```

### 3. direnv Integration (Recommended)

Add to your `.envrc`:

```bash
eval "$(portman export --auto)"
```

Then allow direnv:

```bash
direnv allow
```

Now your environment variables are automatically set:

```bash
echo $POSTGRES_PORT
# Output: 5432

echo $REDIS_PORT
# Output: 6379
```

When you switch worktrees, the ports change automatically!

## Common Workflows

### Working with Multiple Worktrees

```bash
# In worktree main
cd ~/projects/myapp-main
portman book postgres
portman get postgres
# Output: 5432

# In worktree feature
cd ~/projects/myapp-feature
portman book postgres
portman get postgres
# Output: 5433  (different port, no conflict!)
```

### Using with Docker Compose

Update your `docker-compose.yml` to use environment variables:

```yaml
services:
  postgres:
    image: postgres:15
    ports:
      - "${POSTGRES_PORT:-5432}:5432"

  redis:
    image: redis:7
    ports:
      - "${REDIS_PORT:-6379}:6379"
```

Then in your `.envrc`:

```bash
eval "$(portman export --auto)"
```

For custom compose files:

```bash
eval "$(portman export --auto --compose-file docker-compose.prod.yml)"
```

### Working with Multiple Compose Files

If your project uses different compose files for different environments:

```bash
# Development environment
portman book --auto --compose-file docker-compose.dev.yml

# Production environment
portman book --auto --compose-file docker-compose.prod.yml

# Staging environment
portman book --auto --compose-file compose.staging.yaml
```

The `--compose-file` option works with both relative and absolute paths.

### Manual Port Allocation

Prefer a specific port:

```bash
portman book postgres --port 5555
```

Book multiple services:

```bash
portman book postgres
portman book redis
portman book mongodb
```

### List All Allocations

See all port allocations across all contexts:

```bash
portman list
```

See allocations for the current context only:

```bash
portman list --current
```

### Clean Up

Release a specific service in the current context:

```bash
portman release postgres
```

Release all ports for the current context:

```bash
portman release --all
```

Remove allocations for deleted worktrees:

```bash
portman prune
```

Remove stale allocations (not accessed in 30 days):

```bash
portman prune --stale 30
```

## Commands Reference

### `portman book`

Book a port for a service.

```bash
# Book with auto-assigned port
portman book <service>

# Book with preferred port
portman book <service> --port <port>

# Auto-discover from docker-compose.yml
portman book --auto

# Auto-discover from custom compose file
portman book --auto --compose-file docker-compose.prod.yml
portman book --auto -f compose.staging.yaml
```

### `portman get`

Get the allocated port for a service (for scripting).

```bash
portman get <service>

# With quiet output (just the port number)
portman get <service> --quiet
```

### `portman export`

Export environment variables for direnv.

```bash
# Manual services
portman export postgres redis

# Auto-discover from docker-compose.yml
portman export --auto

# Auto-discover from custom compose file
portman export --auto --compose-file docker-compose.prod.yml

# With custom format
portman export postgres --format "POSTGRES_URL=postgresql://localhost:{port}/db"
```

### `portman list`

List all port allocations.

```bash
# All contexts
portman list

# Current context only
portman list --current

# Show system ports
portman list --system
```

### `portman release`

Release port allocations.

```bash
# Release specific service
portman release <service>

# Release all in current context
portman release --all
```

### `portman prune`

Clean up orphaned or stale allocations.

```bash
# Dry run (show what would be removed)
portman prune --dry-run

# Remove orphaned allocations
portman prune

# Remove allocations not accessed in N days
portman prune --stale 30

# Force without confirmation
portman prune --force
```

### `portman init`

Initialize direnv integration.

```bash
# Add export to .envrc
portman init

# Just show the command
portman init --print
```

### `portman config`

Manage port ranges.

```bash
# Show current configuration
portman config --show

# Set port range for a service
portman config --set-range postgres:5400-5500
```

### `portman status`

Show system information and diagnostics.

```bash
portman status
```

### `portman discover`

Discover services from docker-compose files without booking them.

```bash
# Discover from standard compose files
portman discover

# Discover from custom compose file
portman discover --compose-file docker-compose.prod.yml
portman discover -f compose.staging.yaml
```

Shows what services would be booked with `portman book --auto`.

## How It Works

1. **Context Detection**: Portman generates a unique hash based on your project path and git worktree
2. **Database**: Port allocations are stored in a SQLite database at `~/.local/share/portman/allocations.db`
3. **Port Allocation**:
   - Checks if port is already allocated for this context
   - Scans system for ports in use
   - Allocates from service-specific ranges (e.g., 5432-5532 for PostgreSQL)
   - Guarantees machine-wide uniqueness
4. **direnv Integration**: Exports environment variables that update automatically when you switch directories

## Configuration

Port ranges are configurable per service. Default ranges:

- PostgreSQL: 5432-5532
- Redis: 6379-6479
- MongoDB: 27017-27117
- MySQL: 3306-3406

Set custom ranges:

```bash
portman config --set-range postgres:5400-5500
```

## Requirements

- Python 3.10 or higher
- Git (for context detection)
- direnv (optional, for automatic environment variable management)

## License

MIT

## Contributing

Contributions are welcome! Please open an issue or pull request on [GitHub](https://github.com/jpoutrin/portman-cli).
