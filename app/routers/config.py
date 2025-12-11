"""Environment variable management routes."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.dokku import DokkuClient

router = APIRouter(prefix="/config", tags=["config"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/{app_name}", response_class=HTMLResponse)
async def config_list(request: Request, app_name: str):
    """List environment variables."""
    client = DokkuClient()
    config = await client.config_list(app_name)

    return templates.TemplateResponse(
        "components/config_list.html",
        {"request": request, "app_name": app_name, "config": config},
    )


@router.get("/{app_name}/form", response_class=HTMLResponse)
async def config_form(request: Request, app_name: str, key: str = "", value: str = ""):
    """Show add/edit config form."""
    return templates.TemplateResponse(
        "components/config_form.html",
        {"request": request, "app_name": app_name, "key": key, "value": value, "is_edit": bool(key)},
    )


@router.post("/{app_name}/set", response_class=HTMLResponse)
async def config_set(
    request: Request,
    app_name: str,
    key: str = Form(...),
    value: str = Form(...),
    restart: bool = Form(True),
):
    """Set an environment variable."""
    client = DokkuClient()
    await client.config_set(app_name, key, value, restart=restart)

    # Return updated config list
    config = await client.config_list(app_name)
    return templates.TemplateResponse(
        "components/config_list.html",
        {"request": request, "app_name": app_name, "config": config, "message": f"Set {key} successfully"},
    )


@router.post("/{app_name}/unset/{key}", response_class=HTMLResponse)
async def config_unset(
    request: Request,
    app_name: str,
    key: str,
    restart: bool = True,
):
    """Unset an environment variable."""
    client = DokkuClient()
    await client.config_unset(app_name, key, restart=restart)

    # Return updated config list
    config = await client.config_list(app_name)
    return templates.TemplateResponse(
        "components/config_list.html",
        {"request": request, "app_name": app_name, "config": config, "message": f"Removed {key} successfully"},
    )


