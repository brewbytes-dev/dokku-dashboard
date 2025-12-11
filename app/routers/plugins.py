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
    import os
    
    plugins = []
    
    # Read plugins from filesystem (more reliable than dokku command)
    plugin_dir = "/var/lib/dokku/plugins/enabled"
    try:
        if os.path.exists(plugin_dir):
            for plugin_name in sorted(os.listdir(plugin_dir)):
                if plugin_name.startswith("."):
                    continue
                
                # Try to get plugin info file
                info_file = f"{plugin_dir}/{plugin_name}/plugin.toml"
                description = ""
                version = "enabled"
                
                if os.path.exists(info_file):
                    try:
                        with open(info_file, "r") as f:
                            for line in f:
                                if "description" in line:
                                    description = line.split("=", 1)[1].strip().strip('"')
                                elif "version" in line:
                                    version = line.split("=", 1)[1].strip().strip('"')
                    except:
                        pass
                
                plugin = {
                    "name": plugin_name,
                    "version": version,
                    "description": description,
                }
                
                # Get apps using this plugin
                plugin["apps"] = await _get_plugin_apps(plugin_name)
                plugins.append(plugin)
    except OSError:
        pass
    
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

