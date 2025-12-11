# Dokku Dashboard

A modern web UI for managing Dokku applications. Built with FastAPI, HTMX, and Tailwind CSS.

## Features

- **App Management**: View all apps, start/stop/restart/rebuild
- **Live Logs**: Real-time log streaming with SSE
- **Environment Variables**: View, add, edit, delete config vars
- **Modern UI**: Dark theme, responsive design with HTMX interactivity

## Requirements

- Python 3.12+
- SSH access to Dokku server
- Authentik for SSO (optional)

## Quick Start

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DASHBOARD_DOKKU_HOST=your-dokku-server
export DASHBOARD_DOKKU_SSH_KEY=/path/to/ssh/key

# Run
uvicorn app.main:app --reload
```

### Deploy to Dokku

```bash
# Create app
dokku apps:create dokku-dashboard

# Set config
dokku config:set dokku-dashboard \
    DASHBOARD_DOKKU_HOST=localhost \
    DASHBOARD_DOKKU_USER=dokku

# Deploy
git push dokku main
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DASHBOARD_DOKKU_HOST` | Dokku server hostname | `128.140.127.105` |
| `DASHBOARD_DOKKU_USER` | SSH user | `dokku` |
| `DASHBOARD_DOKKU_SSH_KEY` | Path to SSH private key | `/root/.ssh/id_rsa` |
| `DASHBOARD_DEBUG` | Enable debug mode | `false` |

## Security

- All routes protected by Authentik forward-auth
- SSH key with limited Dokku permissions
- Only predefined Dokku commands are allowed

## License

MIT

