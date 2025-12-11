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
        if self.use_docker:
            return await self._app_info_docker(app_name)
        return await self._app_info_ssh(app_name)

    async def _app_info_docker(self, app_name: str) -> App:
        """Get app info from Docker/filesystem - fast."""
        import os
        
        # Get status from Docker
        status = await self._app_status_docker(app_name)
        
        # Read domains from VHOST
        domains = []
        vhost_path = f"/home/dokku/{app_name}/VHOST"
        try:
            with open(vhost_path, "r") as f:
                domains = [line.strip() for line in f if line.strip()]
        except (FileNotFoundError, OSError):
            pass
        
        # Count containers
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-q",
            "--filter", f"label=com.dokku.app-name={app_name}",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        container_count = len([line for line in stdout.decode().strip().split("\n") if line])
        
        return App(
            name=app_name,
            status=status,
            container_count=container_count,
            domains=domains,
            deploy_source="docker",  # We don't have this info without SSH
            web_url=f"https://{domains[0]}" if domains else "",
        )

    async def _app_info_ssh(self, app_name: str) -> App:
        """Get app info via SSH (slower)."""
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
        import os
        
        # Get all Dokku containers with their states
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-a",
            "--filter", "label=com.dokku.app-name",
            "--format", '{"name":"{{.Label "com.dokku.app-name"}}","state":"{{.State}}","status":"{{.Status}}"}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        
        # Parse container info
        app_status = {}  # app_name -> state
        for line in stdout.decode().strip().split("\n"):
            if line:
                try:
                    data = json.loads(line)
                    name = data["name"]
                    state = data["state"].lower()
                    status_text = data["status"].lower()
                    
                    # Detect transitional states
                    if "restarting" in state or "restarting" in status_text:
                        state = "restarting"
                    elif state == "created":
                        state = "starting"
                    
                    # Priority: restarting > starting > running > exited
                    if name not in app_status:
                        app_status[name] = state
                    elif state == "restarting":
                        app_status[name] = state
                    elif state == "starting" and app_status[name] not in ["restarting"]:
                        app_status[name] = state
                    elif state == "running" and app_status[name] not in ["restarting", "starting"]:
                        app_status[name] = state
                except json.JSONDecodeError:
                    continue
        
        # Get all app directories (including apps with no containers)
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
            
            # Get status
            status_str = app_status.get(name, "stopped")
            if status_str == "running":
                status = AppStatus.RUNNING
            elif status_str == "restarting":
                status = AppStatus.RESTARTING
            elif status_str == "starting":
                status = AppStatus.STARTING
            elif status_str in ("exited", "dead", "stopped"):
                status = AppStatus.STOPPED
            else:
                status = AppStatus.UNKNOWN
            
            # Read real domain from VHOST file
            domains = []
            vhost_path = f"/home/dokku/{name}/VHOST"
            try:
                with open(vhost_path, "r") as f:
                    domains = [line.strip() for line in f if line.strip()]
            except (FileNotFoundError, OSError):
                pass
            
            web_url = f"https://{domains[0]}" if domains else ""
            
            apps.append(App(
                name=name,
                status=status,
                domains=domains,
                web_url=web_url,
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
        if self.use_docker:
            return await self._app_start_docker(app_name)
        return await self.run(f"ps:start {app_name}", timeout=60)

    async def app_stop(self, app_name: str) -> str:
        """Stop an app."""
        if self.use_docker:
            return await self._app_stop_docker(app_name)
        return await self.run(f"ps:stop {app_name}", timeout=60)

    async def app_restart(self, app_name: str) -> str:
        """Restart an app."""
        if self.use_docker:
            return await self._app_restart_docker(app_name)
        return await self.run(f"ps:restart {app_name}", timeout=120)

    async def app_rebuild(self, app_name: str) -> str:
        """Rebuild an app."""
        if self.use_docker:
            return await self._app_rebuild_docker(app_name)
        return await self.run(f"ps:rebuild {app_name}", timeout=300)

    async def _app_start_docker(self, app_name: str) -> str:
        """Start app containers directly."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "start",
            *await self._get_container_names(app_name),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode() or stderr.decode()

    async def _app_stop_docker(self, app_name: str) -> str:
        """Stop app containers directly."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "stop",
            *await self._get_container_names(app_name),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode() or stderr.decode()

    async def _app_restart_docker(self, app_name: str) -> str:
        """Restart app containers directly."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "restart",
            *await self._get_container_names(app_name),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode() or stderr.decode()

    async def _app_rebuild_docker(self, app_name: str) -> str:
        """Rebuild via dokku command directly."""
        proc = await asyncio.create_subprocess_exec(
            "dokku", "ps:rebuild", app_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        return stdout.decode() or stderr.decode()

    async def _get_container_names(self, app_name: str) -> list[str]:
        """Get all container names for an app."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-aq",
            "--filter", f"label=com.dokku.app-name={app_name}",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip().split("\n")

    async def config_list(self, app_name: str) -> list[EnvVar]:
        """Get environment variables for an app."""
        if self.use_docker:
            return await self._config_list_docker(app_name)
        return await self._config_list_ssh(app_name)

    async def _config_list_docker(self, app_name: str) -> list[EnvVar]:
        """Get config from ENV file - instant."""
        env_vars = []
        sensitive_keys = {"password", "secret", "key", "token", "api", "private"}
        
        env_path = f"/home/dokku/{app_name}/ENV"
        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    # Parse KEY="VALUE" or KEY=VALUE
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        
                        # Check if sensitive
                        is_sensitive = any(s in key.lower() for s in sensitive_keys)
                        
                        env_vars.append(EnvVar(key=key, value=value, is_sensitive=is_sensitive))
        except (FileNotFoundError, OSError):
            pass
        
        return sorted(env_vars, key=lambda e: e.key)

    async def _config_list_ssh(self, app_name: str) -> list[EnvVar]:
        """Get config via SSH (slower)."""
        output = await self.run(f"config:show {app_name}")
        return self._parse_config(output)

    async def config_set(self, app_name: str, key: str, value: str, restart: bool = True) -> str:
        """Set an environment variable."""
        if self.use_docker:
            return await self._config_set_docker(app_name, key, value, restart)
        restart_flag = "" if restart else "--no-restart"
        # Escape value for shell
        escaped_value = value.replace("'", "'\"'\"'")
        return await self.run(f"config:set {restart_flag} {app_name} {key}='{escaped_value}'", timeout=120)

    async def config_unset(self, app_name: str, key: str, restart: bool = True) -> str:
        """Unset an environment variable."""
        if self.use_docker:
            return await self._config_unset_docker(app_name, key, restart)
        restart_flag = "" if restart else "--no-restart"
        return await self.run(f"config:unset {restart_flag} {app_name} {key}", timeout=120)

    async def _config_set_docker(self, app_name: str, key: str, value: str, restart: bool = True) -> str:
        """Set config using dokku command directly."""
        restart_flag = [] if restart else ["--no-restart"]
        # Escape value for shell
        escaped_value = value.replace("'", "'\"'\"'")
        
        proc = await asyncio.create_subprocess_exec(
            "dokku", "config:set", *restart_flag, app_name, f"{key}='{escaped_value}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        return stdout.decode() or stderr.decode()

    async def _config_unset_docker(self, app_name: str, key: str, restart: bool = True) -> str:
        """Unset config using dokku command directly."""
        restart_flag = [] if restart else ["--no-restart"]
        
        proc = await asyncio.create_subprocess_exec(
            "dokku", "config:unset", *restart_flag, app_name, key,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        return stdout.decode() or stderr.decode()

    async def logs_stream(self, app_name: str, lines: int = 100) -> AsyncIterator[str]:
        """Stream logs from an app."""
        if self.use_docker:
            async for line in self._logs_stream_docker(app_name, lines):
                yield line
        else:
            async with await self._connect() as conn:
                async with conn.create_process(f"logs {app_name} -t -n {lines}") as proc:
                    async for line in proc.stdout:
                        yield line.rstrip("\n")

    async def _logs_stream_docker(self, app_name: str, lines: int = 100) -> AsyncIterator[str]:
        """Stream logs directly from Docker."""
        containers = await self._get_container_names(app_name)
        if not containers or not containers[0]:
            return
        
        # Stream from first web container
        proc = await asyncio.create_subprocess_exec(
            "docker", "logs", "-f", "-n", str(lines), "-t", containers[0],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield line.decode().rstrip("\n")

    async def logs_recent(self, app_name: str, lines: int = 100) -> str:
        """Get recent logs."""
        if self.use_docker:
            return await self._logs_recent_docker(app_name, lines)
        return await self.run(f"logs {app_name} -n {lines}")

    async def _logs_recent_docker(self, app_name: str, lines: int = 100) -> str:
        """Get recent logs directly from Docker."""
        containers = await self._get_container_names(app_name)
        if not containers or not containers[0]:
            return "No containers found"
        
        proc = await asyncio.create_subprocess_exec(
            "docker", "logs", "-n", str(lines), "-t", containers[0],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode()

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

    async def get_app_scaling(self, app_name: str) -> dict:
        """Get app scaling information."""
        from app.dokku.models import ProcessScale
        
        proc = await asyncio.create_subprocess_exec(
            "dokku", "ps:scale", app_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        
        processes = []
        for line in stdout.decode().strip().split("\n"):
            if ":" in line and not line.startswith("---") and not line.startswith("==="):
                parts = line.split(":")
                if len(parts) == 2:
                    proc_type = parts[0].strip()
                    qty = parts[1].strip()
                    try:
                        processes.append(ProcessScale(
                            process_type=proc_type,
                            quantity=int(qty)
                        ))
                    except ValueError:
                        pass
        
        return {"processes": processes}

    async def get_app_network_config(self, app_name: str) -> dict:
        """Get app network configuration."""
        proc = await asyncio.create_subprocess_exec(
            "dokku", "network:report", app_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        
        config = {
            "attached_networks": [],
            "bind_all_interfaces": False,
            "initial_network": "",
        }
        
        for line in stdout.decode().strip().split("\n"):
            if "Network attach post deploy:" in line:
                networks = line.split(":", 1)[1].strip()
                if networks:
                    config["attached_networks"] = networks.split()
            elif "Network bind all interfaces:" in line:
                config["bind_all_interfaces"] = "true" in line.lower()
            elif "Network initial network:" in line:
                config["initial_network"] = line.split(":", 1)[1].strip()
        
        # Get port mappings from proxy:report
        proc = await asyncio.create_subprocess_exec(
            "dokku", "proxy:report", app_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        
        port_map = []
        for line in stdout.decode().strip().split("\n"):
            if "Proxy port map:" in line:
                ports = line.split(":", 1)[1].strip()
                if ports:
                    port_map = ports.split()
        
        config["port_mappings"] = port_map
        
        return config

    async def get_app_storage_mounts(self, app_name: str) -> list[dict]:
        """Get app storage mounts."""
        proc = await asyncio.create_subprocess_exec(
            "dokku", "storage:report", app_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        
        mounts = []
        for line in stdout.decode().strip().split("\n"):
            if ("Storage build mounts:" in line or 
                "Storage deploy mounts:" in line or 
                "Storage run mounts:" in line):
                mount_info = line.split(":", 1)[1].strip()
                if mount_info and mount_info != "none":
                    for mount in mount_info.split():
                        if ":" in mount:
                            host, container = mount.split(":", 1)
                            mounts.append({
                                "host_path": host,
                                "container_path": container,
                                "type": "bind" if not host.startswith("/") else "volume"
                            })
        
        return mounts

    async def get_app_ssl_status(self, app_name: str) -> dict:
        """Get app SSL certificate status."""
        proc = await asyncio.create_subprocess_exec(
            "dokku", "letsencrypt:list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        
        for line in stdout.decode().strip().split("\n"):
            if line.strip().startswith(app_name):
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        expiry_str = " ".join(parts[1:3])
                        days_str = parts[3].split("d,")[0] if "d," in parts[3] else "0"
                        days_until_expiry = int(days_str)
                        
                        return {
                            "enabled": True,
                            "expiry_date": expiry_str,
                            "days_until_expiry": days_until_expiry,
                        }
                    except (ValueError, IndexError):
                        pass
        
        return {"enabled": False}

    async def get_app_health_checks(self, app_name: str) -> dict:
        """Get app health check configuration."""
        proc = await asyncio.create_subprocess_exec(
            "dokku", "checks:report", app_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        
        config = {
            "disabled": [],
            "skipped": [],
            "wait_to_retire": 60,
        }
        
        for line in stdout.decode().strip().split("\n"):
            if "Checks disabled list:" in line:
                disabled = line.split(":", 1)[1].strip()
                if disabled and disabled != "none":
                    config["disabled"] = disabled.split()
            elif "Checks skipped list:" in line:
                skipped = line.split(":", 1)[1].strip()
                if skipped and skipped != "none":
                    config["skipped"] = skipped.split()
            elif "wait to retire:" in line.lower():
                try:
                    wait = line.split(":", 1)[1].strip()
                    config["wait_to_retire"] = int(wait)
                except ValueError:
                    pass
        
        return config

