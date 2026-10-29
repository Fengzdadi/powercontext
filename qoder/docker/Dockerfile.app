FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY app/pyproject.toml app/uv.lock ./
COPY app/examradar/ examradar/
RUN uv sync --frozen --no-dev

COPY app/static/ static/

# Pre-download the embedding model into the image so the app never touches
# the network at runtime (HF_HUB_OFFLINE=1 below). fastembed reads
# FASTEMBED_CACHE_PATH when no cache_dir is passed. Build arg HF_ENDPOINT
# lets networks that reach huggingface.co poorly use a mirror, e.g.
# docker compose build --build-arg HF_ENDPOINT=https://hf-mirror.com
# (or HF_ENDPOINT=... in the .env file passed to compose).
ARG HF_ENDPOINT
ENV FASTEMBED_CACHE_PATH=/opt/fastembed-cache
RUN HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}" \
    uv run --frozen python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-zh-v1.5')"

ENV APP_HOST=0.0.0.0
ENV APP_PORT=18800
ENV HF_HUB_OFFLINE=1

EXPOSE 18800

CMD ["uv", "run", "--no-sync", "uvicorn", "examradar.main:app", "--host", "0.0.0.0", "--port", "18800"]
