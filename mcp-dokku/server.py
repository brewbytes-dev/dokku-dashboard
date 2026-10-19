import asyncio
import os
import subprocess

from fastmcp.exceptions import ToolError
from fastmcp import FastMCP
from fastmcp.server.auth.providers.github import GitHubProvider

from security import require_allowed_github_user

HOST = "mcp.brewbytes.dev"
SSH_KEY = "/run/secrets/dokku/id_ed25519"
MAX_OUTPUT_CHARS = 32_000
JWT_SIGNING_KEY = os.environ["JWT_SIGNING_KEY"]
if len(JWT_SIGNING_KEY) < 32:
    raise RuntimeError("JWT_SIGNING_KEY must contain at least 32 characters.")

auth = GitHubProvider(
    client_id=os.environ["GITHUB_CLIENT_ID"],
    client_secret=os.environ["GITHUB_CLIENT_SECRET"],
    required_scopes=["read:user"],
    base_url=f"https://{HOST}",
    jwt_signing_key=JWT_SIGNING_KEY,
)

mcp = FastMCP("Dokku root shell", auth=auth)


def run_ssh_command(command: str) -> str:
    if not command or len(command) > 8192 or "\0" in command:
        raise ToolError("Command must be non-empty and at most 8192 characters.")

    try:
        result = subprocess.run(
            [
                "ssh",
                "-F",
                "/dev/null",
                "-i",
                SSH_KEY,
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "UserKnownHostsFile=/app/known_hosts",
                "-o",
                "ConnectTimeout=10",
                f"root@{HOST}",
                command,
            ],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError("Root command exceeded the 120 second limit.") from exc
    except OSError as exc:
        raise ToolError("Could not start the SSH client.") from exc

    output = result.stdout + result.stderr
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
    if result.returncode:
        raise ToolError(
            f"Root command exited with status {result.returncode}.\n{output}"
        )
    return output or "Command completed with no output."


@mcp.tool
async def run_root_command(command: str) -> str:
    """Run an arbitrary shell command as root on the Dokku host.

    Command output can contain server secrets and will be returned to the agent.
    """
    require_allowed_github_user()
    return await asyncio.to_thread(run_ssh_command, command)


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        log_level="warning",
        show_banner=False,
        uvicorn_config={"access_log": False},
    )
