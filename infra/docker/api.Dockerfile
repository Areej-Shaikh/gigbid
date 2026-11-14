# GigBid API + web UI (one URL). Build from the repo root:
#   docker build -f infra/docker/api.Dockerfile -t gigbid-api .
# The MCP servers (marketplace, portfolio) run inside this container as stdio subprocesses.

# ---- 1. build the React app ----
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

# ---- 2. Python runtime ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# requirements.txt is frozen on Windows: drop Windows-only packages for the Linux image
COPY requirements.txt .
RUN grep -viE "^(pywin32)==" requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt

COPY agent/ agent/
COPY apps/__init__.py apps/__init__.py
COPY apps/api/ apps/api/
COPY mcp_servers/ mcp_servers/
COPY rag/ rag/
COPY gigsim/ gigsim/
COPY data/ data/
COPY scripts/ scripts/
COPY infra/docker/start.sh /app/start.sh
COPY --from=web /web/dist apps/web/dist

# run as a non-root user. chmod u+w: files copied from a Windows/OneDrive checkout can arrive
# without write permission, and SQLite must be able to create its checkpoint file in data/processed
RUN useradd --create-home gigbid && chown -R gigbid /app && chmod -R u+w /app && chmod +x /app/start.sh
USER gigbid

EXPOSE 8000
CMD ["/app/start.sh"]
