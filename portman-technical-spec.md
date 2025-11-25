# 📋 Spécification Technique : **Portman**

> Port Manager for Development Environments

## 1. Vue d'ensemble

### 1.1 Problème à résoudre

Lors du développement sur plusieurs branches/worktrees d'un même projet (ou plusieurs projets), les services Docker (PostgreSQL, Redis, etc.) entrent en conflit sur les ports. Les développeurs doivent manuellement gérer les allocations de ports, ce qui est source d'erreurs et de perte de temps.

### 1.2 Solution

**Portman** est un CLI qui :
- Maintient un registre SQLite centralisé au niveau utilisateur (`~/.local/share/portman/`)
- Identifie automatiquement le contexte (projet + branche) via un hash MD5
- Alloue des ports uniques machine-wide sans conflit
- S'intègre nativement avec `direnv` pour une expérience transparente
- Découvre automatiquement les services depuis `docker-compose.yml`
- Nettoie automatiquement les allocations orphelines (pruning)

### 1.3 Philosophie

- **Zero configuration statique** : pas de fichiers `.env` générés à maintenir
- **Dynamique first** : les ports sont résolus à la volée via direnv
- **Convention over configuration** : fonctionne out-of-the-box
- **Machine-wide uniqueness** : impossible d'avoir des conflits entre projets

---

## 2. Architecture

### 2.1 Structure du projet

```
portman/
├── pyproject.toml              # Config uv/hatch, metadata PyPI
├── README.md
├── LICENSE                     # MIT
├── CHANGELOG.md
├── .github/
│   └── workflows/
│       ├── ci.yml              # Tests, lint, typecheck
│       ├── release.yml         # Publication PyPI + GitHub Releases
│       └── homebrew.yml        # Update homebrew formula
├── src/
│   └── portman/
│       ├── __init__.py
│       ├── __main__.py         # Entry point: python -m portman
│       ├── cli.py              # Typer CLI
│       ├── db.py               # Couche SQLite
│       ├── context.py          # Détection contexte (hash MD5)
│       ├── allocator.py        # Logique d'allocation
│       ├── discovery.py        # Scan docker-compose.yml
│       ├── system.py           # Scan ports système (ss/lsof)
│       ├── direnv.py           # Helpers direnv
│       ├── pruner.py           # Nettoyage allocations orphelines
│       └── config.py           # Configuration (ranges, etc.)
├── tests/
│   ├── conftest.py
│   ├── test_cli.py
│   ├── test_db.py
│   ├── test_context.py
│   ├── test_allocator.py
│   ├── test_discovery.py
│   └── test_pruner.py
├── homebrew/
│   └── portman.rb              # Formula Homebrew
└── scripts/
    └── install.sh              # Script d'installation one-liner
```

### 2.2 Dépendances

```toml
[project]
name = "portman-cli"
version = "0.1.0"
description = "Port Manager for Development Environments"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
keywords = ["docker", "ports", "development", "direnv", "worktree"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]

dependencies = [
    "typer>=0.12.0",
    "rich>=13.0.0",
    "pyyaml>=6.0",
    "platformdirs>=4.0.0",
]

[project.scripts]
portman = "portman.cli:app"

[project.urls]
Homepage = "https://github.com/USERNAME/portman"
Documentation = "https://github.com/USERNAME/portman#readme"
Repository = "https://github.com/USERNAME/portman"
Issues = "https://github.com/USERNAME/portman/issues"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/portman"]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "mypy>=1.8.0",
    "ruff>=0.3.0",
]
```

---

## 3. Base de données

### 3.1 Emplacement

```
~/.local/share/portman/
├── registry.db          # Base SQLite
└── portman.log          # Logs (optionnel, rotation)
```

Sur macOS : `~/Library/Application Support/portman/`
Sur Windows : `%APPDATA%\portman\`

Utiliser `platformdirs` pour la détection cross-platform.

### 3.2 Schéma SQLite

```sql
-- Version du schéma pour migrations futures
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY
);
INSERT INTO schema_version VALUES (1);

-- Allocations de ports
CREATE TABLE allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Identification du contexte
    context_hash TEXT NOT NULL,           -- MD5 tronqué 12 chars
    context_path TEXT NOT NULL,           -- Chemin absolu (pour affichage/debug)
    context_label TEXT,                   -- Label humain: "myproject/feature-x"
    
    -- Service
    service TEXT NOT NULL,                -- "postgres", "redis", etc.
    
    -- Port alloué
    port INTEGER NOT NULL UNIQUE,         -- Contrainte UNIQUE = unicité machine-wide
    
    -- Métadonnées
    container_port INTEGER,               -- Port interne au container (ex: 5432)
    env_var TEXT,                         -- Variable d'env associée (ex: "PG_PORT")
    source TEXT,                          -- Origine: "docker-compose.yml", "manual"
    
    -- Timestamps
    created_at TEXT DEFAULT (datetime('now')),
    last_accessed_at TEXT DEFAULT (datetime('now')),
    
    -- Contrainte d'unicité par contexte+service
    UNIQUE(context_hash, service)
);

-- Index pour performance
CREATE INDEX idx_allocations_context ON allocations(context_hash);
CREATE INDEX idx_allocations_port ON allocations(port);
CREATE INDEX idx_allocations_last_accessed ON allocations(last_accessed_at);

-- Configuration des ranges de ports par service
CREATE TABLE port_ranges (
    service TEXT PRIMARY KEY,
    range_start INTEGER NOT NULL,
    range_end INTEGER NOT NULL
);

-- Ranges par défaut
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
```

---

## 4. Contexte et Identification

### 4.1 Calcul du context_hash

Le hash identifie de manière unique un environnement de développement :

```python
# src/portman/context.py

import hashlib
import subprocess
from pathlib import Path
from dataclasses import dataclass

@dataclass
class Context:
    hash: str           # "a1b2c3d4e5f6"
    path: str           # "/home/user/projects/myapp"
    label: str          # "myapp/feature-auth"
    remote: str | None  # "git@github.com:user/myapp.git"
    branch: str | None  # "feature-auth"

def get_context(path: Path | None = None) -> Context:
    """
    Génère un contexte unique pour le répertoire courant.
    
    Stratégie de hashing (par ordre de priorité):
    1. Git remote origin + branche courante (si repo git)
    2. Chemin absolu (fallback)
    
    Le hash est basé sur des identifiants stables qui ne changent pas
    si on déplace le projet (pour le cas git).
    """
    path = (path or Path.cwd()).resolve()
    
    remote = _get_git_remote(path)
    branch = _get_git_branch(path)
    
    if remote and branch:
        # Hash basé sur l'identité Git (stable même si on déplace le projet)
        identity = f"{remote}:{branch}"
        label = f"{_extract_repo_name(remote)}/{branch}"
    else:
        # Fallback: chemin absolu
        identity = str(path)
        label = path.name
    
    hash_value = hashlib.md5(identity.encode()).hexdigest()[:12]
    
    return Context(
        hash=hash_value,
        path=str(path),
        label=label,
        remote=remote,
        branch=branch,
    )

def _get_git_remote(path: Path) -> str | None:
    """Récupère l'URL du remote origin."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None

def _get_git_branch(path: Path) -> str | None:
    """Récupère la branche courante."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        
        # Fallback pour detached HEAD (utiliser le nom du worktree)
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None

def _extract_repo_name(remote_url: str) -> str:
    """Extrait le nom du repo depuis l'URL remote."""
    # git@github.com:user/repo.git -> repo
    # https://github.com/user/repo.git -> repo
    name = remote_url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name
```

---

## 5. Allocateur de Ports

### 5.1 Logique d'allocation

```python
# src/portman/allocator.py

import socket
from .db import Database
from .system import SystemScanner

class PortAllocationError(Exception):
    """Raised when no port can be allocated."""
    pass

class PortAllocator:
    """Alloue des ports en garantissant l'unicité machine-wide."""
    
    def __init__(self, db: Database):
        self.db = db
        self.system = SystemScanner()
    
    def allocate(
        self,
        service: str,
        context_hash: str,
        preferred_port: int | None = None,
    ) -> int:
        """
        Alloue un port pour un service dans un contexte donné.
        
        Stratégie:
        1. Si déjà alloué pour ce contexte+service → retourner le port existant
        2. Si preferred_port spécifié et disponible → l'utiliser
        3. Sinon → trouver le premier port libre dans le range du service
        
        Returns:
            Le port alloué
            
        Raises:
            PortAllocationError: Si aucun port disponible
        """
        # 1. Vérifier si déjà alloué
        existing = self.db.get_allocation(context_hash, service)
        if existing:
            self.db.touch_allocation(existing['id'])
            return existing['port']
        
        # 2. Collecter les ports indisponibles
        unavailable = self._get_unavailable_ports()
        
        # 3. Essayer le port préféré
        if preferred_port and self._is_port_available(preferred_port, unavailable):
            return preferred_port
        
        # 4. Trouver dans le range du service
        port_range = self.db.get_port_range(service)
        
        for port in range(port_range.start, port_range.end + 1):
            if self._is_port_available(port, unavailable):
                return port
        
        # 5. Fallback sur le range default
        if service != "default":
            default_range = self.db.get_port_range("default")
            for port in range(default_range.start, default_range.end + 1):
                if self._is_port_available(port, unavailable):
                    return port
        
        raise PortAllocationError(f"No available port for service '{service}'")
    
    def _get_unavailable_ports(self) -> set[int]:
        """Retourne l'ensemble des ports non disponibles."""
        db_ports = self.db.get_all_allocated_ports()
        system_ports = self.system.get_listening_ports()
        return db_ports | system_ports
    
    def _is_port_available(self, port: int, unavailable: set[int]) -> bool:
        """Vérifie si un port est disponible."""
        if port in unavailable:
            return False
        return self.system.is_port_bindable(port)
```

### 5.2 Scanner système

```python
# src/portman/system.py

import socket
import subprocess
import re

class SystemScanner:
    """Scan les ports utilisés sur le système."""
    
    def get_listening_ports(self) -> set[int]:
        """Retourne les ports TCP en écoute."""
        ports = set()
        
        # Essayer ss (Linux, rapide)
        ports.update(self._scan_ss())
        
        # Fallback lsof (macOS, universel)
        if not ports:
            ports.update(self._scan_lsof())
        
        # Fallback netstat (Windows, universel)
        if not ports:
            ports.update(self._scan_netstat())
        
        return ports
    
    def is_port_bindable(self, port: int) -> bool:
        """Test si on peut bind sur ce port."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', port))
                return True
        except OSError:
            return False
    
    def _scan_ss(self) -> set[int]:
        """Scan via ss (Linux)."""
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
                match = re.search(r':(\d+)\s', line)
                if match:
                    ports.add(int(match.group(1)))
            return ports
        except (subprocess.SubprocessError, FileNotFoundError):
            return set()
    
    def _scan_lsof(self) -> set[int]:
        """Scan via lsof (macOS/Linux)."""
        try:
            result = subprocess.run(
                ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ports = set()
            for line in result.stdout.splitlines()[1:]:  # Skip header
                match = re.search(r':(\d+)\s', line)
                if match:
                    ports.add(int(match.group(1)))
            return ports
        except (subprocess.SubprocessError, FileNotFoundError):
            return set()
    
    def _scan_netstat(self) -> set[int]:
        """Scan via netstat (Windows/universel)."""
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
                    match = re.search(r':(\d+)\s', line)
                    if match:
                        ports.add(int(match.group(1)))
            return ports
        except (subprocess.SubprocessError, FileNotFoundError):
            return set()
```

---

## 6. Découverte automatique

### 6.1 Scanner docker-compose

```python
# src/portman/discovery.py

from pathlib import Path
from dataclasses import dataclass
import re
import yaml

@dataclass
class DiscoveredService:
    name: str                    # Nom du service docker
    container_port: int          # Port interne (ex: 5432)
    env_var: str | None          # Variable d'env si ${VAR}:port
    source: str                  # Fichier source

def discover_services(path: Path | None = None) -> list[DiscoveredService]:
    """
    Découvre les services nécessitant des ports depuis docker-compose.yml.
    
    Parse les définitions de ports:
    - "8080:80"           → host explicite, ignorer
    - "${PG_PORT}:5432"   → variable d'env → à allouer
    - "5432"              → port seul → à allouer
    """
    path = path or Path.cwd()
    services = []
    
    # Chercher les fichiers compose
    compose_files = [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ]
    
    for filename in compose_files:
        compose_path = path / filename
        if compose_path.exists():
            services.extend(_parse_compose_file(compose_path))
    
    return services

def _parse_compose_file(file_path: Path) -> list[DiscoveredService]:
    """Parse un fichier docker-compose."""
    services = []
    
    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, IOError):
        return services
    
    if not data or "services" not in data:
        return services
    
    for svc_name, svc_config in data.get("services", {}).items():
        if not isinstance(svc_config, dict):
            continue
        
        for port_def in svc_config.get("ports", []):
            parsed = _parse_port_definition(port_def, svc_name)
            if parsed:
                parsed.source = str(file_path)
                services.append(parsed)
    
    return services

def _parse_port_definition(port_def, service_name: str) -> DiscoveredService | None:
    """
    Parse une définition de port docker-compose.
    
    Formats supportés:
    - "8080:80"           → port explicite, ignorer
    - "${PG_PORT}:5432"   → variable → à allouer
    - "$PG_PORT:5432"     → variable → à allouer  
    - "5432"              → port seul → à allouer
    - { published: 8080, target: 80 }  → format long
    """
    if isinstance(port_def, dict):
        # Format long
        published = port_def.get("published")
        target = port_def.get("target")
        
        if isinstance(published, str) and published.startswith("$"):
            # Variable d'environnement
            env_var = published.lstrip("${").rstrip("}")
            return DiscoveredService(
                name=service_name,
                container_port=int(target) if target else 0,
                env_var=env_var,
                source="",
            )
        return None  # Port explicite, ignorer
    
    port_str = str(port_def)
    
    # Variable: ${VAR}:5432 ou $VAR:5432
    var_match = re.match(r'^\$\{?(\w+)\}?:(\d+)(?:/\w+)?$', port_str)
    if var_match:
        return DiscoveredService(
            name=service_name,
            container_port=int(var_match.group(2)),
            env_var=var_match.group(1),
            source="",
        )
    
    # Port seul: "5432"
    if port_str.isdigit():
        return DiscoveredService(
            name=service_name,
            container_port=int(port_str),
            env_var=f"{service_name.upper()}_PORT",
            source="",
        )
    
    # Sinon c'est un port explicite (ex: "8080:80"), ignorer
    return None

def infer_service_type(service_name: str, image: str | None = None) -> str:
    """
    Infère le type de service pour déterminer le range de ports.
    
    Basé sur le nom du service ou l'image Docker.
    """
    name_lower = service_name.lower()
    image_lower = (image or "").lower()
    
    mappings = {
        ("postgres", "pg", "psql"): "postgres",
        ("mysql", "mariadb"): "mysql",
        ("redis",): "redis",
        ("mongo", "mongodb"): "mongodb",
        ("elastic", "elasticsearch"): "elasticsearch",
        ("meili", "meilisearch"): "meilisearch",
        ("rabbit", "rabbitmq"): "rabbitmq",
        ("kafka",): "kafka",
    }
    
    for keywords, service_type in mappings.items():
        for keyword in keywords:
            if keyword in name_lower or keyword in image_lower:
                return service_type
    
    return "default"
```

---

## 7. Intégration direnv

### 7.1 Principe

L'intégration direnv est le cœur de l'expérience utilisateur. Une seule ligne dans `.envrc` suffit :

```bash
eval "$(portman export --auto)"
```

Cette commande :
1. Détecte le contexte (hash MD5 du repo+branche)
2. Découvre les services depuis `docker-compose.yml`
3. Book automatiquement les ports manquants
4. Retourne les exports shell

### 7.2 Helper functions

```python
# src/portman/direnv.py

DIRENV_HELPER = '''
# Portman helper function for direnv
# Add to ~/.config/direnv/direnvrc

use_portman() {
    eval "$(portman export --auto)"
}
'''

ENVRC_TEMPLATE = '''# Portman integration
eval "$(portman export --auto)"
'''

def generate_envrc_content() -> str:
    """Génère le contenu recommandé pour .envrc."""
    return 'eval "$(portman export --auto)"'
```

### 7.3 Output de la commande export

```bash
# Ce que `portman export --auto` produit:
export POSTGRES_PORT=5432
export REDIS_PORT=6379
export COMPOSE_PROJECT_NAME=myapp-feature-auth
```

---

## 8. Pruning (Nettoyage)

### 8.1 Logique de pruning

```python
# src/portman/pruner.py

from pathlib import Path
from dataclasses import dataclass
from .db import Database
from .context import get_context

@dataclass  
class PruneResult:
    removed: list[dict]      # Allocations supprimées
    kept: list[dict]         # Allocations conservées
    errors: list[str]        # Erreurs rencontrées

class Pruner:
    """Nettoie les allocations orphelines."""
    
    def __init__(self, db: Database):
        self.db = db
    
    def prune(self, dry_run: bool = False) -> PruneResult:
        """
        Supprime les allocations dont le contexte n'existe plus.
        
        Vérifications:
        1. Le chemin (context_path) existe-t-il encore ?
        2. Si c'est un repo git, la branche existe-t-elle encore ?
        
        Args:
            dry_run: Si True, ne supprime rien, retourne juste ce qui serait supprimé
            
        Returns:
            PruneResult avec les détails
        """
        result = PruneResult(removed=[], kept=[], errors=[])
        
        allocations = self.db.get_all_allocations()
        
        for alloc in allocations:
            try:
                if self._is_orphan(alloc):
                    if not dry_run:
                        self.db.delete_allocation(alloc['id'])
                    result.removed.append(alloc)
                else:
                    result.kept.append(alloc)
            except Exception as e:
                result.errors.append(f"{alloc['context_label']}: {e}")
        
        return result
    
    def _is_orphan(self, allocation: dict) -> bool:
        """Détermine si une allocation est orpheline."""
        context_path = Path(allocation['context_path'])
        
        # Le chemin n'existe plus
        if not context_path.exists():
            return True
        
        # Si c'est un repo git, vérifier que le hash correspond toujours
        try:
            current_context = get_context(context_path)
            if current_context.hash != allocation['context_hash']:
                # Le contexte a changé (ex: branche différente)
                # Ce n'est pas orphelin, c'est un contexte différent
                return False
        except Exception:
            pass
        
        return False
    
    def prune_stale(self, days: int = 30, dry_run: bool = False) -> PruneResult:
        """
        Supprime les allocations non accédées depuis X jours.
        
        Utile pour nettoyer les vieux projets même si le dossier existe encore.
        """
        result = PruneResult(removed=[], kept=[], errors=[])
        
        stale_allocations = self.db.get_stale_allocations(days=days)
        
        for alloc in stale_allocations:
            if not dry_run:
                self.db.delete_allocation(alloc['id'])
            result.removed.append(alloc)
        
        return result
```

---

## 9. CLI (Typer)

### 9.1 Commandes principales

```python
# src/portman/cli.py

import typer
from rich.console import Console
from rich.table import Table
from typing import Optional
from pathlib import Path

app = typer.Typer(
    name="portman",
    help="Port Manager for Development Environments",
    no_args_is_help=True,
)
console = Console()

# ============================================================================
# COMMANDES PRINCIPALES
# ============================================================================

@app.command()
def get(
    service: str = typer.Argument(..., help="Service name (e.g., postgres, redis)"),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Output only the port number"),
    book: bool = typer.Option(True, "--book/--no-book", help="Auto-book if not allocated"),
):
    """
    Get the port for a service in current context.
    
    If not allocated and --book is set (default), automatically allocates a port.
    
    Examples:
        portman get postgres
        portman get redis -q
        PGPORT=$(portman get postgres -q)
    """
    ...

@app.command()
def book(
    service: Optional[str] = typer.Argument(None, help="Service name to book"),
    port: Optional[int] = typer.Option(None, "-p", "--port", help="Preferred port"),
    auto: bool = typer.Option(False, "--auto", help="Auto-discover from docker-compose.yml"),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Minimal output"),
):
    """
    Book port(s) for service(s) in current context.
    
    Examples:
        portman book postgres
        portman book postgres --port 5433
        portman book --auto
    """
    ...

@app.command()
def release(
    service: Optional[str] = typer.Argument(None, help="Service to release"),
    all: bool = typer.Option(False, "--all", help="Release all ports for current context"),
):
    """
    Release port allocation(s) for current context.
    
    Examples:
        portman release postgres
        portman release --all
    """
    ...

@app.command(name="export")
def export_cmd(
    auto: bool = typer.Option(False, "--auto", help="Auto-discover and book services"),
    format: str = typer.Option("shell", "--format", "-f", help="Output format: shell, json, env"),
):
    """
    Export port allocations as environment variables.
    
    Designed for use with direnv:
        eval "$(portman export --auto)"
    
    Examples:
        portman export
        portman export --auto
        portman export --format json
    """
    ...

# ============================================================================
# COMMANDES D'INFORMATION
# ============================================================================

@app.command()
def status(
    all: bool = typer.Option(False, "-a", "--all", help="Show all contexts, not just current"),
    live: bool = typer.Option(False, "--live", help="Check if ports are actually listening"),
):
    """
    Show port allocations status.
    
    Examples:
        portman status
        portman status --all
        portman status --all --live
    """
    ...

@app.command()
def context():
    """
    Show current context information.
    
    Displays:
        - Context hash
        - Context path  
        - Context label
        - Git remote (if applicable)
        - Git branch (if applicable)
    """
    ...

@app.command()
def discover():
    """
    Discover services from docker-compose.yml without booking.
    
    Shows what services would be booked with `portman book --auto`.
    """
    ...

# ============================================================================
# COMMANDES DE MAINTENANCE
# ============================================================================

@app.command()
def prune(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be removed"),
    stale_days: Optional[int] = typer.Option(None, "--stale", help="Also remove allocations not accessed in N days"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """
    Remove orphaned port allocations.
    
    Checks if context paths still exist and removes allocations for deleted projects.
    
    Examples:
        portman prune --dry-run
        portman prune
        portman prune --stale 30
    """
    ...

@app.command()
def gc():
    """
    Alias for `portman prune`. Garbage collect orphaned allocations.
    """
    ...

# ============================================================================
# COMMANDES DE CONFIGURATION
# ============================================================================

@app.command()
def init(
    shell: bool = typer.Option(False, "--shell", help="Output shell integration snippet"),
    direnv: bool = typer.Option(False, "--direnv", help="Output direnv integration snippet"),
):
    """
    Initialize portman and show setup instructions.
    
    Examples:
        portman init
        portman init --direnv
    """
    ...

@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
    set_range: Optional[str] = typer.Option(None, "--set-range", help="Set port range: service:start-end"),
):
    """
    Manage portman configuration.
    
    Examples:
        portman config --show
        portman config --set-range postgres:5500-5599
    """
    ...

# ============================================================================
# ENTRÉE PRINCIPALE
# ============================================================================

def main():
    app()

if __name__ == "__main__":
    main()
```

### 9.2 Exemples de sortie

```bash
# portman status --all --live
┌──────────────┬─────────────────────┬──────────┬──────┬────────────┐
│ Context      │ Label               │ Service  │ Port │ Status     │
├──────────────┼─────────────────────┼──────────┼──────┼────────────┤
│ a1b2c3d4e5f6 │ myapp/feature-auth  │ postgres │ 5432 │ ● LISTEN   │
│ a1b2c3d4e5f6 │ myapp/feature-auth  │ redis    │ 6379 │ ○ free     │
│ f6e5d4c3b2a1 │ myapp/main          │ postgres │ 5433 │ ● LISTEN   │
│ 123456789abc │ other-project/main  │ postgres │ 5434 │ ○ free     │
└──────────────┴─────────────────────┴──────────┴──────┴────────────┘

# portman export --auto
export POSTGRES_PORT=5432
export REDIS_PORT=6379
export COMPOSE_PROJECT_NAME=myapp-feature-auth

# portman prune --dry-run
Would remove 2 orphaned allocation(s):
  - deleted-project/main: postgres (5435)
  - deleted-project/main: redis (6380)

Run without --dry-run to remove.

# portman context
Context: a1b2c3d4e5f6
  Path:   /home/user/projects/myapp
  Label:  myapp/feature-auth
  Remote: git@github.com:user/myapp.git
  Branch: feature-auth
```

---

## 10. Installation

### 10.1 Via uv/pip (recommandé)

```bash
# Installation globale avec uv
uv tool install portman-cli

# Ou avec pipx
pipx install portman-cli

# Ou avec pip
pip install --user portman-cli
```

### 10.2 Via Homebrew

```ruby
# homebrew/portman.rb
class Portman < Formula
  include Language::Python::Virtualenv

  desc "Port Manager for Development Environments"
  homepage "https://github.com/USERNAME/portman"
  url "https://github.com/USERNAME/portman/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "..."
  license "MIT"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    system "#{bin}/portman", "--version"
  end
end
```

### 10.3 Script one-liner

```bash
# scripts/install.sh
#!/bin/bash
set -e

echo "Installing portman..."

# Detect package manager
if command -v uv &> /dev/null; then
    uv tool install portman-cli
elif command -v pipx &> /dev/null; then
    pipx install portman-cli
elif command -v pip &> /dev/null; then
    pip install --user portman-cli
else
    echo "Error: No Python package manager found (uv, pipx, or pip)"
    exit 1
fi

echo "✓ portman installed successfully"
echo ""
echo "Quick start:"
echo "  cd your-project"
echo "  echo 'eval \"\$(portman export --auto)\"' >> .envrc"
echo "  direnv allow"
```

Installation via curl :

```bash
curl -fsSL https://raw.githubusercontent.com/USERNAME/portman/main/scripts/install.sh | bash
```

### 10.4 Depuis le repo Git

```bash
# Clone et installation en mode éditable
git clone https://github.com/USERNAME/portman.git
cd portman
uv sync
uv tool install -e .
```

---

## 11. CI/CD

### 11.1 Tests et Lint

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Install uv
        uses: astral-sh/setup-uv@v4
        
      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: uv sync --all-extras
      
      - name: Run linter
        run: uv run ruff check src tests
      
      - name: Run type checker
        run: uv run mypy src
      
      - name: Run tests
        run: uv run pytest --cov=portman --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
```

### 11.2 Release et Publication

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write  # For PyPI trusted publishing
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Install uv
        uses: astral-sh/setup-uv@v4
      
      - name: Build package
        run: uv build
      
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
      
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: dist/*
```

---

## 12. Documentation utilisateur (README.md)

```markdown
# 🚢 Portman

> Port Manager for Development Environments

Stop fighting port conflicts. Portman automatically manages port allocations
across all your projects and git worktrees.

## Features

- 🔒 **Machine-wide uniqueness** - No more port conflicts between projects
- 🔍 **Auto-discovery** - Detects services from docker-compose.yml
- ⚡ **direnv integration** - Ports resolved dynamically on `cd`
- 🧹 **Auto-cleanup** - Prunes allocations for deleted projects
- 📦 **Zero config** - Works out of the box

## Installation

\`\`\`bash
# With uv (recommended)
uv tool install portman-cli

# With pipx
pipx install portman-cli

# With Homebrew (coming soon)
brew install portman
\`\`\`

## Quick Start

1. **Add to your `.envrc`:**

\`\`\`bash
eval "$(portman export --auto)"
\`\`\`

2. **Allow direnv:**

\`\`\`bash
direnv allow
\`\`\`

3. **Done!** Your ports are now managed automatically.

\`\`\`bash
$ echo $POSTGRES_PORT
5432

$ cd ../other-project
direnv: loading .envrc
$ echo $POSTGRES_PORT
5433  # Different port, no conflict!
\`\`\`

## Commands

| Command | Description |
|---------|-------------|
| `portman get <service>` | Get port for a service |
| `portman book <service>` | Book a port explicitly |
| `portman book --auto` | Auto-book from docker-compose.yml |
| `portman export --auto` | Export ports (for direnv) |
| `portman status` | Show current allocations |
| `portman status --all` | Show all allocations |
| `portman prune` | Clean up orphaned allocations |
| `portman context` | Show current context info |

## How it Works

Portman identifies your context using a hash of:
- Git remote URL + current branch (for git repos)
- Absolute path (fallback)

This means:
- Same project, different branches = different ports
- Move your project folder = same ports (git-based)
- Delete a project = ports automatically freed on `portman prune`

## License

MIT
```

---

## 13. Tests

### 13.1 Structure des tests

```python
# tests/conftest.py

import pytest
from pathlib import Path
import tempfile
import subprocess

@pytest.fixture
def temp_dir():
    """Temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def mock_db(temp_dir):
    """Database for tests."""
    from portman.db import Database
    db_path = temp_dir / "test.db"
    return Database(db_path)

@pytest.fixture
def mock_git_repo(temp_dir):
    """Create a mock git repository."""
    repo_dir = temp_dir / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:test/repo.git"],
        cwd=repo_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "main"],
        cwd=repo_dir,
        capture_output=True,
    )
    return repo_dir
```

### 13.2 Tests unitaires

```python
# tests/test_context.py

from portman.context import get_context

def test_context_from_git_repo(mock_git_repo):
    ctx = get_context(mock_git_repo)
    
    assert ctx.hash is not None
    assert len(ctx.hash) == 12
    assert ctx.remote == "git@github.com:test/repo.git"
    assert ctx.branch == "main"
    assert "repo" in ctx.label

def test_context_from_plain_directory(temp_dir):
    ctx = get_context(temp_dir)
    
    assert ctx.hash is not None
    assert ctx.remote is None
    assert ctx.branch is None

def test_context_hash_stability(mock_git_repo):
    ctx1 = get_context(mock_git_repo)
    ctx2 = get_context(mock_git_repo)
    
    assert ctx1.hash == ctx2.hash
```

```python
# tests/test_allocator.py

from portman.allocator import PortAllocator

def test_allocate_new_port(mock_db):
    allocator = PortAllocator(mock_db)
    
    port = allocator.allocate("postgres", "test-context")
    
    assert 5432 <= port <= 5499  # Dans le range postgres

def test_allocate_returns_existing(mock_db):
    allocator = PortAllocator(mock_db)
    
    port1 = allocator.allocate("postgres", "test-context")
    port2 = allocator.allocate("postgres", "test-context")
    
    assert port1 == port2

def test_allocate_different_contexts(mock_db):
    allocator = PortAllocator(mock_db)
    
    port1 = allocator.allocate("postgres", "context-1")
    port2 = allocator.allocate("postgres", "context-2")
    
    assert port1 != port2
```

```python
# tests/test_pruner.py

from portman.pruner import Pruner

def test_prune_removes_orphaned(mock_db, temp_dir):
    # Create allocation for non-existent path
    mock_db.create_allocation(
        context_hash="orphan123",
        context_path="/nonexistent/path",
        context_label="orphan/test",
        service="postgres",
        port=5432,
    )
    
    pruner = Pruner(mock_db)
    result = pruner.prune()
    
    assert len(result.removed) == 1
    assert result.removed[0]['context_hash'] == "orphan123"

def test_prune_keeps_valid(mock_db, temp_dir):
    # Create allocation for existing path
    mock_db.create_allocation(
        context_hash="valid123",
        context_path=str(temp_dir),
        context_label="valid/test",
        service="postgres",
        port=5432,
    )
    
    pruner = Pruner(mock_db)
    result = pruner.prune()
    
    assert len(result.removed) == 0
    assert len(result.kept) == 1
```

---

## 14. Notes d'implémentation

### 14.1 Points d'attention

1. **Thread safety SQLite** : Utiliser `check_same_thread=False` et un lock pour les accès concurrents
2. **Permissions** : Créer le dossier data avec les bonnes permissions (700)
3. **Atomic writes** : Utiliser des transactions pour les opérations critiques
4. **Cross-platform** : Tester sur Linux, macOS. Windows est bonus.
5. **Performance** : Le CLI doit répondre en < 100ms pour ne pas ralentir direnv

### 14.2 Ordre d'implémentation suggéré

1. `db.py` - Couche base de données
2. `context.py` - Détection du contexte
3. `allocator.py` - Allocation des ports
4. `system.py` - Scanner ports système
5. `cli.py` - Commandes `get`, `book`, `release`, `status`
6. `discovery.py` - Parser docker-compose
7. `cli.py` - Commande `export --auto`
8. `pruner.py` - Nettoyage
9. `cli.py` - Commandes `prune`, `init`, `config`
10. Tests complets
11. CI/CD
12. Documentation

### 14.3 Nom du package

- CLI : `portman`
- Package PyPI : `portman-cli` (car `portman` est probablement pris)
- Repo GitHub : `portman`

---

## 15. Future enhancements (v2+)

- [ ] GUI (TUI avec Textual ou Rich)
- [ ] Sync entre machines (fichier de config partageable)
- [ ] Intégration VS Code (extension)
- [ ] Support Windows natif
- [ ] Webhooks / notifications
- [ ] API REST locale pour intégrations tierces
- [ ] Support Podman en plus de Docker

---

*Fin de la spécification technique*
