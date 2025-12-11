"""Log streaming routes."""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from app.dokku import DokkuClient

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/{app_name}", response_class=HTMLResponse)
async def logs_page(request: Request, app_name: str):
    """Log viewer page."""
    return templates.TemplateResponse(
        "logs/viewer.html",
        {"request": request, "app_name": app_name},
    )


@router.get("/{app_name}/recent", response_class=HTMLResponse)
async def recent_logs(request: Request, app_name: str, lines: int = 100):
    """Get recent logs (non-streaming)."""
    client = DokkuClient()
    logs = await client.logs_recent(app_name, lines)

    return templates.TemplateResponse(
        "components/log_content.html",
        {"request": request, "logs": logs, "app_name": app_name},
    )


@router.get("/{app_name}/stream")
async def stream_logs(app_name: str):
    """Stream logs via SSE."""

    async def generate():
        client = DokkuClient()
        try:
            async for line in client.logs_stream(app_name, lines=100):
                # Color code based on log level
                css_class = "log-line"
                line_lower = line.lower()
                if "error" in line_lower or "err" in line_lower:
                    css_class = "log-line log-error"
                elif "warn" in line_lower:
                    css_class = "log-line log-warn"
                elif "info" in line_lower:
                    css_class = "log-line log-info"

                yield {
                    "event": "log",
                    "data": f'<div class="{css_class}">{_escape_html(line)}</div>',
                }
        except asyncio.CancelledError:
            pass
        except Exception as e:
            yield {
                "event": "error",
                "data": f'<div class="log-line log-error">Error: {_escape_html(str(e))}</div>',
            }

    return EventSourceResponse(generate())


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


