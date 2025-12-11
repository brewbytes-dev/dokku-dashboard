"""Authentik authentication middleware."""

from dataclasses import dataclass

from fastapi import Request


@dataclass
class User:
    """Authenticated user from Authentik headers."""

    username: str
    email: str
    name: str
    groups: list[str]
    uid: str

    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return "authentik Admins" in self.groups


def get_current_user(request: Request) -> User | None:
    """Extract user info from Authentik forward-auth headers."""
    username = request.headers.get("X-Authentik-Username")
    if not username:
        return None

    return User(
        username=username,
        email=request.headers.get("X-Authentik-Email", ""),
        name=request.headers.get("X-Authentik-Name", username),
        groups=request.headers.get("X-Authentik-Groups", "").split("|"),
        uid=request.headers.get("X-Authentik-Uid", ""),
    )

