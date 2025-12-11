"""Plugins routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/plugins", tags=["plugins"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_plugins(request: Request):
    """List installed Dokku plugins."""
    import asyncio
    
    # Get list of plugins
    proc = await asyncio.create_subprocess_exec(
        "dokku", "plugin:list",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    
    plugins = []
    for line in stdout.decode().strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("===") or line.startswith("----"):
            continue
        
        # Parse plugin line format: "plugin-name version description"
        parts = line.split(maxsplit=2)
        if len(parts) >= 2:
            plugin = {
                "name": parts[0],
                "version": parts[1],
                "description": parts[2] if len(parts) > 2 else "",
            }
            
            # Get apps using this plugin
            plugin["apps"] = await _get_plugin_apps(parts[0])
            plugins.append(plugin)
    
    return templates.TemplateResponse(
        "plugins/list.html",
        {"request": request, "plugins": plugins},
    )


async def _get_plugin_apps(plugin_name: str) -> list[str]:
    """Get apps using a specific plugin."""
    import asyncio
    import os
    
    apps_using_plugin = []
    
    # Check for service plugins (postgres, redis, mysql, etc.)
    if plugin_name in ["postgres", "redis", "mysql", "mongo", "elasticsearch"]:
        proc = await asyncio.create_subprocess_exec(
            "dokku", f"{plugin_name}:list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        
        for line in stdout.decode().strip().split("\n"):
            if line and not line.startswith("===") and not line.startswith("----"):
                service_name = line.split()[0]
                apps_using_plugin.append(service_name)
    
    # Check for letsencrypt
    elif plugin_name == "letsencrypt":
        try:
            for app_dir in os.listdir("/home/dokku"):
                if app_dir.startswith(".") or app_dir in {"ENV", "VHOST", "tls", "dokkurc"}:
                    continue
                letsencrypt_dir = f"/home/dokku/{app_dir}/letsencrypt"
                if os.path.exists(letsencrypt_dir):
                    apps_using_plugin.append(app_dir)
        except OSError:
            pass
    
    return apps_using_plugin

