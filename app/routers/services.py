"""Services management routes."""

import asyncio
import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.dokku.models import Service

router = APIRouter(prefix="/services", tags=["services"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_services(request: Request):
    """List all Dokku services."""
    services = []
    
    # Get Redis services
    redis_services = await _get_redis_services()
    services.extend(redis_services)
    
    # Get Postgres services
    postgres_services = await _get_postgres_services()
    services.extend(postgres_services)
    
    # Get MySQL services
    mysql_services = await _get_mysql_services()
    services.extend(mysql_services)
    
    # Get Mongo services
    mongo_services = await _get_mongo_services()
    services.extend(mongo_services)
    
    return templates.TemplateResponse(
        "services/list.html",
        {"request": request, "services": services},
    )


async def _get_redis_services() -> list[Service]:
    """Get all Redis services."""
    services = []
    redis_dir = "/var/lib/dokku/services/redis"
    
    try:
        if not os.path.exists(redis_dir):
            return services
        
        for service_name in os.listdir(redis_dir):
            if service_name.startswith("."):
                continue
            
            service_path = f"{redis_dir}/{service_name}"
            if not os.path.isdir(service_path):
                continue
            
            # Get service info using docker
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", f"dokku.redis.{service_name}",
                "--format", "{{.State.Status}}|{{.Config.Image}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            
            status = "stopped"
            version = "unknown"
            
            if stdout:
                parts = stdout.decode().strip().split("|")
                if len(parts) >= 2:
                    status = "running" if parts[0] == "running" else "stopped"
                    version = parts[1].replace("redis:", "").replace("redis/redis:", "")
            
            # Read DSN from ENV file
            dsn = ""
            env_file = f"{service_path}/ENV"
            if os.path.exists(env_file):
                try:
                    with open(env_file, "r") as f:
                        for line in f:
                            if line.startswith("export REDIS_URL="):
                                dsn = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except:
                    pass
            
            # Get linked apps
            linked_apps = await _get_service_links(service_name, "redis")
            
            services.append(Service(
                name=service_name,
                type="redis",
                version=version,
                status=status,
                dsn=dsn,
                linked_apps=linked_apps,
                config_dir=f"{service_path}/config",
                data_dir=f"{service_path}/data",
            ))
    
    except OSError:
        pass
    
    return services


async def _get_postgres_services() -> list[Service]:
    """Get all Postgres services."""
    services = []
    postgres_dir = "/var/lib/dokku/services/postgres"
    
    try:
        if not os.path.exists(postgres_dir):
            return services
        
        for service_name in os.listdir(postgres_dir):
            if service_name.startswith("."):
                continue
            
            service_path = f"{postgres_dir}/{service_name}"
            if not os.path.isdir(service_path):
                continue
            
            # Get service info
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", f"dokku.postgres.{service_name}",
                "--format", "{{.State.Status}}|{{.Config.Image}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            
            status = "stopped"
            version = "unknown"
            
            if stdout:
                parts = stdout.decode().strip().split("|")
                if len(parts) >= 2:
                    status = "running" if parts[0] == "running" else "stopped"
                    version = parts[1].replace("postgres:", "")
            
            # Read DSN
            dsn = ""
            env_file = f"{service_path}/ENV"
            if os.path.exists(env_file):
                try:
                    with open(env_file, "r") as f:
                        for line in f:
                            if "DATABASE_URL=" in line:
                                dsn = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except:
                    pass
            
            linked_apps = await _get_service_links(service_name, "postgres")
            
            services.append(Service(
                name=service_name,
                type="postgres",
                version=version,
                status=status,
                dsn=dsn,
                linked_apps=linked_apps,
                config_dir=f"{service_path}/config",
                data_dir=f"{service_path}/data",
            ))
    
    except OSError:
        pass
    
    return services


async def _get_mysql_services() -> list[Service]:
    """Get all MySQL services."""
    services = []
    mysql_dir = "/var/lib/dokku/services/mysql"
    
    try:
        if not os.path.exists(mysql_dir):
            return services
        
        for service_name in os.listdir(mysql_dir):
            if service_name.startswith("."):
                continue
            
            service_path = f"{mysql_dir}/{service_name}"
            if not os.path.isdir(service_path):
                continue
            
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", f"dokku.mysql.{service_name}",
                "--format", "{{.State.Status}}|{{.Config.Image}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            
            status = "stopped"
            version = "unknown"
            
            if stdout:
                parts = stdout.decode().strip().split("|")
                if len(parts) >= 2:
                    status = "running" if parts[0] == "running" else "stopped"
                    version = parts[1].replace("mysql:", "")
            
            dsn = ""
            env_file = f"{service_path}/ENV"
            if os.path.exists(env_file):
                try:
                    with open(env_file, "r") as f:
                        for line in f:
                            if "DATABASE_URL=" in line:
                                dsn = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except:
                    pass
            
            linked_apps = await _get_service_links(service_name, "mysql")
            
            services.append(Service(
                name=service_name,
                type="mysql",
                version=version,
                status=status,
                dsn=dsn,
                linked_apps=linked_apps,
                config_dir=f"{service_path}/config",
                data_dir=f"{service_path}/data",
            ))
    
    except OSError:
        pass
    
    return services


async def _get_mongo_services() -> list[Service]:
    """Get all Mongo services."""
    services = []
    mongo_dir = "/var/lib/dokku/services/mongo"
    
    try:
        if not os.path.exists(mongo_dir):
            return services
        
        for service_name in os.listdir(mongo_dir):
            if service_name.startswith("."):
                continue
            
            service_path = f"{mongo_dir}/{service_name}"
            if not os.path.isdir(service_path):
                continue
            
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", f"dokku.mongo.{service_name}",
                "--format", "{{.State.Status}}|{{.Config.Image}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            
            status = "stopped"
            version = "unknown"
            
            if stdout:
                parts = stdout.decode().strip().split("|")
                if len(parts) >= 2:
                    status = "running" if parts[0] == "running" else "stopped"
                    version = parts[1].replace("mongo:", "")
            
            dsn = ""
            env_file = f"{service_path}/ENV"
            if os.path.exists(env_file):
                try:
                    with open(env_file, "r") as f:
                        for line in f:
                            if "MONGO_URL=" in line or "DATABASE_URL=" in line:
                                dsn = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except:
                    pass
            
            linked_apps = await _get_service_links(service_name, "mongo")
            
            services.append(Service(
                name=service_name,
                type="mongo",
                version=version,
                status=status,
                dsn=dsn,
                linked_apps=linked_apps,
                config_dir=f"{service_path}/config",
                data_dir=f"{service_path}/data",
            ))
    
    except OSError:
        pass
    
    return services


async def _get_service_links(service_name: str, service_type: str) -> list[str]:
    """Get apps linked to a service."""
    linked_apps = []
    
    # Check each app's ENV file for this service
    try:
        for app_dir in os.listdir("/home/dokku"):
            if app_dir.startswith(".") or app_dir in {"ENV", "VHOST", "tls", "dokkurc"}:
                continue
            
            env_file = f"/home/dokku/{app_dir}/ENV"
            if os.path.exists(env_file):
                try:
                    with open(env_file, "r") as f:
                        content = f.read()
                        # Check if service is referenced in env
                        if f"dokku.{service_type}.{service_name}" in content or f"{service_name}" in content:
                            linked_apps.append(app_dir)
                except:
                    pass
    except OSError:
        pass
    
    return linked_apps

