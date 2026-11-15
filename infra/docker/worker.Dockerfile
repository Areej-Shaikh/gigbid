# GigBid worker (E1): scheduled scouting of saved searches on Arq + Redis. Build from the repo root:
#   docker build -f infra/docker/worker.Dockerfile -t gigbid-worker .
# No web build and no server: it calls the API (API_URL) to start analyses, so it needs only the Python code.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN grep -viE "^(pywin32)==" requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt

COPY agent/ agent/
COPY apps/__init__.py apps/__init__.py
COPY apps/api/ apps/api/
COPY rag/ rag/
COPY worker/ worker/

RUN useradd --create-home gigbid && chown -R gigbid /app && chmod -R u+w /app
USER gigbid

CMD ["python", "-m", "arq", "worker.main.WorkerSettings"]
