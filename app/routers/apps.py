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
    app = await client.app_info(app_name)
    config = await client.config_list(app_name)

    return templates.TemplateResponse(
        "apps/detail.html",
        {"request": request, "app": app, "config": config},
    )


@router.post("/{app_name}/start", response_class=HTMLResponse)
async def start_app(request: Request, app_name: str):
    """Start an app."""
    client = DokkuClient()
    await client.app_start(app_name)
    app = await client.app_info(app_name)

    return templates.TemplateResponse(
        "components/app_card.html",
        {"request": request, "app": app},
    )


@router.post("/{app_name}/stop", response_class=HTMLResponse)
async def stop_app(request: Request, app_name: str):
    """Stop an app."""
    client = DokkuClient()
    await client.app_stop(app_name)
    app = await client.app_info(app_name)

    return templates.TemplateResponse(
        "components/app_card.html",
        {"request": request, "app": app},
    )


@router.post("/{app_name}/restart", response_class=HTMLResponse)
async def restart_app(request: Request, app_name: str):
    """Restart an app."""
    client = DokkuClient()
    await client.app_restart(app_name)
    app = await client.app_info(app_name)

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

