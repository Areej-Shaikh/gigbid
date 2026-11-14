# GigSim marketplace simulator. Build from the repo root:
#   docker build -f infra/docker/gigsim.Dockerfile -t gigbid-gigsim .
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install $(grep -iE "^(fastapi|uvicorn|pydantic|pydantic_core|starlette)==" requirements.txt)

COPY gigsim/ gigsim/
COPY data/processed/gigsim_db.json data/processed/price_stats.json data/processed/

RUN useradd --create-home gigsim && chown -R gigsim /app
USER gigsim

EXPOSE 8001
CMD ["uvicorn", "gigsim.app:app", "--host", "0.0.0.0", "--port", "8001"]
