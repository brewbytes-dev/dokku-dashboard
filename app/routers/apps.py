"""App management routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.dokku import DokkuClient

router = APIRouter(prefix="/apps", tags=["apps"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_apps(request: Request):
    """List all Dokku apps."""
    client = DokkuClient()
    apps = await client.get_all_apps()

    return templates.TemplateResponse(
        "apps/list.html",
        {"request": request, "apps": apps},
    )


@router.get("/{app_name}", response_class=HTMLResponse)
async def app_detail(request: Request, app_name: str):
    """Get app details."""
    client = DokkuClient()
    
    # Gather all app information in parallel
    import asyncio
    app, config, scaling, network, storage, ssl_status, health = await asyncio.gather(
        client.app_info(app_name),
        client.config_list(app_name),
        client.get_app_scaling(app_name),
        client.get_app_network_config(app_name),
        client.get_app_storage_mounts(app_name),
        client.get_app_ssl_status(app_name),
        client.get_app_health_checks(app_name),
    )

    return templates.TemplateResponse(
        "apps/detail.html",
        {
            "request": request,
            "app": app,
            "config": config,
            "scaling": scaling,
            "network": network,
            "storage": storage,
            "ssl": ssl_status,
            "health": health,
        },
    )


@router.post("/{app_name}/start", response_class=HTMLResponse)
async def start_app(request: Request, app_name: str):
    """Start an app."""
    client = DokkuClient()
    await client.app_start(app_name)
    
    import asyncio
    app, ssl_status = await asyncio.gather(
        client.app_info(app_name),
        client.get_app_ssl_status(app_name),
    )
    
    # Check if called from detail page or list page
    target = request.headers.get("hx-target", "")
    if target == "#app-status":
        return templates.TemplateResponse(
            "components/app_status.html",
            {"request": request, "app": app, "ssl": ssl_status},
        )
    else:
        return templates.TemplateResponse(
            "components/app_card.html",
            {"request": request, "app": app},
        )


@router.post("/{app_name}/stop", response_class=HTMLResponse)
async def stop_app(request: Request, app_name: str):
    """Stop an app."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Stopping app: {app_name}")
        client = DokkuClient()
        result = await client.app_stop(app_name)
        logger.info(f"Stop result: {result}")
        
        import asyncio
        app, ssl_status = await asyncio.gather(
            client.app_info(app_name),
            client.get_app_ssl_status(app_name),
        )
        
        # Check if called from detail page or list page
        target = request.headers.get("hx-target", "")
        logger.info(f"Target: {target}")
        
        if target == "#app-status":
            return templates.TemplateResponse(
                "components/app_status.html",
                {"request": request, "app": app, "ssl": ssl_status},
            )
        else:
            return templates.TemplateResponse(
                "components/app_card.html",
                {"request": request, "app": app},
            )
    except Exception as e:
        logger.error(f"Error stopping app {app_name}: {e}", exc_info=True)
        raise


@router.post("/{app_name}/restart", response_class=HTMLResponse)
async def restart_app(request: Request, app_name: str):
    """Restart an app."""
    client = DokkuClient()
    await client.app_restart(app_name)
    
    import asyncio
    app, ssl_status = await asyncio.gather(
        client.app_info(app_name),
        client.get_app_ssl_status(app_name),
    )
    
    # Check if called from detail page or list page
    target = request.headers.get("hx-target", "")
    if target == "#app-status":
        return templates.TemplateResponse(
            "components/app_status.html",
            {"request": request, "app": app, "ssl": ssl_status},
        )
    else:
        return templates.TemplateResponse(
            "components/app_card.html",
            {"request": request, "app": app},
        )


@router.post("/{app_name}/rebuild", response_class=HTMLResponse)
async def rebuild_app(request: Request, app_name: str):
    """Rebuild an app."""
    client = DokkuClient()
    await client.app_rebuild(app_name)
    app = await client.app_info(app_name)

    return templates.TemplateResponse(
        "components/app_card.html",
        {"request": request, "app": app},
    )


@router.get("/{app_name}/card", response_class=HTMLResponse)
async def app_card(request: Request, app_name: str):
    """Get single app card (for HTMX refresh)."""
    client = DokkuClient()
    app = await client.app_info(app_name)

    return templates.TemplateResponse(
        "components/app_card.html",
        {"request": request, "app": app},
    )


@router.get("/{app_name}/status", response_class=HTMLResponse)
async def app_status(request: Request, app_name: str):
    """Get app status badge (for lazy loading)."""
    client = DokkuClient()
    status = await client.app_status(app_name)

    # Return just the status badge HTML
    status_colors = {
        "running": "bg-green-500",
        "stopped": "bg-red-500",
        "crashed": "bg-orange-500",
        "unknown": "bg-gray-500",
    }
    color = status_colors.get(status.value, "bg-gray-500")

    return HTMLResponse(
        f'<span class="px-2 py-1 text-xs font-medium text-white rounded-full {color}">'
        f'{status.value}</span>'
    )

