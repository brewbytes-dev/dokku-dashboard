"""Dokku client - uses Docker socket when available, SSH as fallback."""

import asyncio
import os
import re
from typing import AsyncIterator

import asyncssh

from app.config import get_settings
from app.dokku.models import App, AppStatus, EnvVar

# Check if we can use Docker directly
DOCKER_SOCKET = "/var/run/docker.sock"
USE_DOCKER = os.path.exists(DOCKER_SOCKET)


class DokkuClient:
    """Dokku client - prefers Docker socket over SSH for speed."""

    def __init__(self):
        settings = get_settings()
        self.host = settings.dokku_host
        self.user = settings.dokku_user
        self.key_path = settings.dokku_ssh_key
        self.use_docker = USE_DOCKER

    async def _connect(self) -> asyncssh.SSHClientConnection:
        """Create SSH connection."""
        return await asyncssh.connect(
            self.host,
            username=self.user,
            client_keys=[self.key_path],
            known_hosts=None,  # Skip host key verification for simplicity
        )

    async def run_fast(self, command: str, timeout: int = 30) -> str:
        """Execute a dokku command using subprocess (faster for large output)."""
        ssh_cmd = [
            "ssh",
            "-i", self.key_path,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            f"{self.user}@{self.host}",
            command,
        ]
        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return stdout.decode() or stderr.decode() or ""
        except asyncio.TimeoutError:
            proc.kill()
            return ""

    async def run(self, command: str, timeout: int = 30) -> str:
        """Execute a dokku command and return output."""
        async with await self._connect() as conn:
            result = await asyncio.wait_for(
                conn.run(command, check=False),
                timeout=timeout,
            )
            return result.stdout or result.stderr or ""

    async def apps_list(self) -> list[str]:
        """Get list of all app names."""
        output = await self.run("apps:list")
        lines = output.strip().split("\n")
        # Skip header line "=====> My Apps"
        return [line.strip() for line in lines[1:] if line.strip()]

    async def app_status(self, app_name: str) -> AppStatus:
        """Get app running status."""
        if self.use_docker:
            return await self._app_status_docker(app_name)
        return await self._app_status_ssh(app_name)

    async def _app_status_docker(self, app_name: str) -> AppStatus:
        """Get app status from Docker - instant."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-q",
            "--filter", f"label=com.dokku.app-name={app_name}",
            "--filter", "status=running",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if stdout.strip():
            return AppStatus.RUNNING
        return AppStatus.STOPPED

    async def _app_status_ssh(self, app_name: str) -> AppStatus:
        """Get app status via SSH (slower)."""
        output = await self.run(f"ps:report {app_name}")

        if "running" in output.lower():
            return AppStatus.RUNNING
        if "stopped" in output.lower():
            return AppStatus.STOPPED
        if "crashed" in output.lower() or "exited" in output.lower():
            return AppStatus.CRASHED
        return AppStatus.UNKNOWN

    async def app_info(self, app_name: str) -> App:
        """Get full app information."""
        # Get status
        status = await self.app_status(app_name)

        # Get domains
        domains_output = await self.run(f"domains:report {app_name}")
        domains = self._parse_domains(domains_output)

        # Get container count
        ps_output = await self.run(f"ps:report {app_name}")
        container_count = self._parse_container_count(ps_output)

        # Get deploy source
        git_output = await self.run(f"git:report {app_name}")
        deploy_source = self._parse_deploy_source(git_output)

        return App(
            name=app_name,
            status=status,
            container_count=container_count,
            domains=domains,
            deploy_source=deploy_source,
            web_url=f"https://{domains[0]}" if domains else "",
        )

    async def get_all_apps(self) -> list[App]:
        """Get all apps with status - uses Docker socket if available."""
        if self.use_docker:
            return await self._get_apps_from_docker()
        return await self._get_apps_from_ssh()

    async def _get_apps_from_docker(self) -> list[App]:
        """Get apps directly from Docker - instant!"""
        import json
        
        # Get all Dokku containers in one Docker API call
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-a",
            "--filter", "label=com.dokku.app-name",
            "--format", '{"name":"{{.Label "com.dokku.app-name"}}","status":"{{.State}}"}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        
        # Parse container info
        app_status = {}  # app_name -> running/stopped
        for line in stdout.decode().strip().split("\n"):
            if line:
                try:
                    data = json.loads(line)
                    name = data["name"]
                    status = data["status"]
                    # If any container for this app is running, mark as running
                    if name not in app_status or status == "running":
                        app_status[name] = status
                except json.JSONDecodeError:
                    continue
        
        # Get all app directories (including apps with no containers)
        import os
        skip_dirs = {"ENV", "VHOST", "tls", "dokkurc", ".basher", ".cache", ".config", ".ssh", ".local"}
        
        apps = []
        try:
            all_dirs = os.listdir("/home/dokku")
        except OSError:
            all_dirs = []
        
        for name in all_dirs:
            # Skip non-app directories
            if name.startswith(".") or name in skip_dirs:
                continue
            
            status_str = app_status.get(name, "stopped")
            if status_str == "running":
                status = AppStatus.RUNNING
            elif status_str in ("exited", "dead"):
                status = AppStatus.STOPPED
            else:
                status = AppStatus.UNKNOWN
            
            apps.append(App(
                name=name,
                status=status,
                web_url=f"https://{name}.brewbytes.dev",
            ))
        
        return sorted(apps, key=lambda a: a.name)

    async def _get_apps_from_ssh(self) -> list[App]:
        """Fallback: Get apps via SSH (slower)."""
        output = await self.run_fast("apps:list", timeout=10)
        
        apps = []
        lines = output.strip().split("\n")
        
        # Skip header line "=====> My Apps"
        for line in lines[1:]:
            name = line.strip()
            if name:
                apps.append(App(
                    name=name,
                    status=AppStatus.UNKNOWN,
                    web_url=f"https://{name}.brewbytes.dev",
                ))
        
        return apps

    async def app_start(self, app_name: str) -> str:
        """Start an app."""
        return await self.run(f"ps:start {app_name}", timeout=60)

    async def app_stop(self, app_name: str) -> str:
        """Stop an app."""
        return await self.run(f"ps:stop {app_name}", timeout=60)

    async def app_restart(self, app_name: str) -> str:
        """Restart an app."""
        return await self.run(f"ps:restart {app_name}", timeout=120)

    async def app_rebuild(self, app_name: str) -> str:
        """Rebuild an app."""
        return await self.run(f"ps:rebuild {app_name}", timeout=300)

    async def config_list(self, app_name: str) -> list[EnvVar]:
        """Get environment variables for an app."""
        output = await self.run(f"config:show {app_name}")
        return self._parse_config(output)

    async def config_set(self, app_name: str, key: str, value: str, restart: bool = True) -> str:
        """Set an environment variable."""
        restart_flag = "" if restart else "--no-restart"
        # Escape value for shell
        escaped_value = value.replace("'", "'\"'\"'")
        return await self.run(f"config:set {restart_flag} {app_name} {key}='{escaped_value}'", timeout=120)

    async def config_unset(self, app_name: str, key: str, restart: bool = True) -> str:
        """Unset an environment variable."""
        restart_flag = "" if restart else "--no-restart"
        return await self.run(f"config:unset {restart_flag} {app_name} {key}", timeout=120)

    async def logs_stream(self, app_name: str, lines: int = 100) -> AsyncIterator[str]:
        """Stream logs from an app."""
        async with await self._connect() as conn:
            async with conn.create_process(f"logs {app_name} -t -n {lines}") as proc:
                async for line in proc.stdout:
                    yield line.rstrip("\n")

    async def logs_recent(self, app_name: str, lines: int = 100) -> str:
        """Get recent logs."""
        return await self.run(f"logs {app_name} -n {lines}")

    # Parser methods
    def _parse_domains(self, output: str) -> list[str]:
        """Parse domains from domains:report output."""
        domains = []
        for line in output.split("\n"):
            if "Domains app vhosts:" in line:
                # Extract domains after the colon
                parts = line.split(":", 1)
                if len(parts) > 1:
                    domain_str = parts[1].strip()
                    domains = [d.strip() for d in domain_str.split() if d.strip()]
        return domains

    def _parse_container_count(self, output: str) -> int:
        """Parse container count from ps:report output."""
        for line in output.split("\n"):
            if "Processes:" in line or "Running:" in line:
                match = re.search(r"(\d+)", line)
                if match:
                    return int(match.group(1))
        return 0

    def _parse_deploy_source(self, output: str) -> str:
        """Parse deploy source from git:report output."""
        for line in output.split("\n"):
            if "Git deploy branch:" in line:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    return parts[1].strip()
        return "unknown"

    def _parse_config(self, output: str) -> list[EnvVar]:
        """Parse environment variables from config:show output."""
        env_vars = []
        sensitive_keys = {"password", "secret", "key", "token", "api", "private"}

        for line in output.split("\n"):
            if ":" in line and not line.startswith("="):
                # Split on first colon only
                parts = line.split(":", 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()

                    # Skip header lines
                    if key.startswith("===="):
                        continue

                    # Check if sensitive
                    is_sensitive = any(s in key.lower() for s in sensitive_keys)

                    env_vars.append(EnvVar(key=key, value=value, is_sensitive=is_sensitive))

        return env_vars

