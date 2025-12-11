"""Dokku data models."""

from dataclasses import dataclass, field
from enum import Enum


class AppStatus(str, Enum):
    """Application status."""

    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
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

