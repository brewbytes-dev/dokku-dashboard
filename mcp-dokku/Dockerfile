FROM python:3.12-slim

ENV HOME=/home/mcp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin mcp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY mcp-dokku/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp-dokku/server.py mcp-dokku/security.py ./
COPY mcp-dokku/known_hosts ./known_hosts
RUN chmod 0444 /app/known_hosts

USER 10001:10001
EXPOSE 8000
CMD ["python", "server.py"]
