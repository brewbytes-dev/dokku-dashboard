"""System information routes."""

import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/system", tags=["system"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def system_info(request: Request):
    """Show Dokku system information."""
    import asyncio
    
    # Get Dokku version
    proc = await asyncio.create_subprocess_exec(
        "dokku", "version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    dokku_version = stdout.decode().strip()
    
    # Get disk usage
    proc = await asyncio.create_subprocess_exec(
        "df", "-h", "/",
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    disk_lines = stdout.decode().strip().split("\n")
    disk_info = disk_lines[1].split() if len(disk_lines) > 1 else []
    
    # Get memory usage
    proc = await asyncio.create_subprocess_exec(
        "free", "-h",
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    mem_lines = stdout.decode().strip().split("\n")
    mem_info = mem_lines[1].split() if len(mem_lines) > 1 else []
    
    # Get Docker info
    proc = await asyncio.create_subprocess_exec(
        "docker", "info", "--format", "{{.ServerVersion}}",
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    docker_version = stdout.decode().strip()
    
    # Count Docker objects
    proc = await asyncio.create_subprocess_exec(
        "docker", "ps", "-aq",
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    container_count = len([l for l in stdout.decode().strip().split("\n") if l])
    
    proc = await asyncio.create_subprocess_exec(
        "docker", "images", "-q",
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    image_count = len([l for l in stdout.decode().strip().split("\n") if l])
    
    proc = await asyncio.create_subprocess_exec(
        "docker", "volume", "ls", "-q",
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    volume_count = len([l for l in stdout.decode().strip().split("\n") if l])
    
    # Count Dokku apps
    try:
        app_count = len([d for d in os.listdir("/home/dokku") 
                        if not d.startswith(".") and d not in {"ENV", "VHOST", "tls", "dokkurc"}])
    except OSError:
        app_count = 0
    
    system_data = {
        "dokku_version": dokku_version,
        "docker_version": docker_version,
        "disk": {
            "size": disk_info[1] if len(disk_info) > 1 else "N/A",
            "used": disk_info[2] if len(disk_info) > 2 else "N/A",
            "available": disk_info[3] if len(disk_info) > 3 else "N/A",
            "percent": disk_info[4] if len(disk_info) > 4 else "N/A",
        },
        "memory": {
            "total": mem_info[1] if len(mem_info) > 1 else "N/A",
            "used": mem_info[2] if len(mem_info) > 2 else "N/A",
            "free": mem_info[3] if len(mem_info) > 3 else "N/A",
        },
        "apps": app_count,
        "containers": container_count,
        "images": image_count,
        "volumes": volume_count,
    }
    
    return templates.TemplateResponse(
        "system/info.html",
        {"request": request, "system": system_data},
    )

