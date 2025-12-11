"""Dokku data models."""

from dataclasses import dataclass, field
from enum import Enum


class AppStatus(str, Enum):
    """Application status."""

    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    RESTARTING = "restarting"
    STARTING = "starting"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


@dataclass
class App:
    """Dokku application."""

    name: str
    status: AppStatus = AppStatus.UNKNOWN
    container_count: int = 0
    domains: list[str] = field(default_factory=list)
    created_at: str = ""
    deploy_source: str = ""
    web_url: str = ""

    @property
    def primary_domain(self) -> str | None:
        """Get primary domain."""
        return self.domains[0] if self.domains else None


@dataclass
class EnvVar:
    """Environment variable."""

    key: str
    value: str
    is_sensitive: bool = False

    @property
    def masked_value(self) -> str:
        """Get masked value for display."""
        if self.is_sensitive or len(self.value) > 50:
            return "••••••••"
        return self.value


@dataclass
class Service:
    """Dokku service (Redis, Postgres, MySQL, etc)."""

    name: str
    type: str  # redis, postgres, mysql, mongo
    version: str
    status: str  # running, stopped
    dsn: str
    linked_apps: list[str] = field(default_factory=list)
    config_dir: str = ""
    data_dir: str = ""

    @property
    def masked_dsn(self) -> str:
        """Get masked DSN for display."""
        if ":" in self.dsn and "@" in self.dsn:
            # redis://:password@host:port format
            parts = self.dsn.split("@")
            if len(parts) == 2:
                return f"•••••••@{parts[1]}"
        return "••••••••"


@dataclass
class SSLCertificate:
    """SSL certificate information."""

    app_name: str
    expiry_date: str
    days_until_expiry: int
    days_until_renewal: int
    auto_renew: bool = True

    @property
    def status_color(self) -> str:
        """Get color based on days until expiry."""
        if self.days_until_expiry > 60:
            return "green"
        elif self.days_until_expiry > 30:
            return "yellow"
        elif self.days_until_expiry > 7:
            return "orange"
        return "red"


@dataclass
class ProcessScale:
    """Process scaling information."""

    process_type: str  # web, worker, release
    quantity: int


