from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token

ALLOWED_GITHUB_LOGIN = "brewbytes-dev"


def require_allowed_github_user() -> None:
    token = get_access_token()
    login = token.claims.get("login") if token else None
    if not isinstance(login, str) or login.casefold() != ALLOWED_GITHUB_LOGIN:
        raise ToolError("This MCP server is restricted to its owner’s GitHub account.")
