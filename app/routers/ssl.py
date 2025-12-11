"""SSL certificates management routes."""

import asyncio
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.dokku.models import SSLCertificate

router = APIRouter(prefix="/ssl", tags=["ssl"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_certificates(request: Request):
    """List all SSL certificates."""
    certificates = await _get_ssl_certificates()
    
    # Sort by expiry date (soonest first)
    certificates.sort(key=lambda c: c.days_until_expiry)
    
    return templates.TemplateResponse(
        "ssl/list.html",
        {"request": request, "certificates": certificates},
    )


async def _get_ssl_certificates() -> list[SSLCertificate]:
    """Get all SSL certificates from letsencrypt."""
    certificates = []
    
    # Run dokku letsencrypt:list
    proc = await asyncio.create_subprocess_exec(
        "dokku", "letsencrypt:list",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    
    if not stdout:
        return certificates
    
    lines = stdout.decode().strip().split("\n")
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith("---") or "App name" in line:
            continue
        
        # Parse line format: "app_name    2026-01-20 05:25:37    39d, 8h, 3m, 2s    9d, 8h, 3m, 2s"
        parts = line.split()
        if len(parts) < 4:
            continue
        
        app_name = parts[0]
        
        # Parse expiry date
        try:
            expiry_str = " ".join(parts[1:3])  # "2026-01-20 05:25:37"
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, IndexError):
            continue
        
        # Parse "39d, 8h, 3m, 2s" format
        days_until_expiry = 0
        try:
            time_parts = " ".join(parts[3:])  # Join all remaining parts
            if "d," in time_parts:
                days_str = time_parts.split("d,")[0].strip()
                days_until_expiry = int(days_str)
        except (ValueError, IndexError):
            days_until_expiry = 0
        
        # Calculate days until renewal (typically 30 days before expiry)
        days_until_renewal = max(0, days_until_expiry - 30)
        
        certificates.append(SSLCertificate(
            app_name=app_name,
            expiry_date=expiry_str,
            days_until_expiry=days_until_expiry,
            days_until_renewal=days_until_renewal,
            auto_renew=True,  # Assume auto-renew is enabled
        ))
    
    return certificates

