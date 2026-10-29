FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /usr/local/bin/

WORKDIR /app

# 1. Install dependencies only (--no-install-project, source not copied yet):
#    this layer stays cached when application code changes.
COPY app/pyproject.toml app/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2. Pre-download the embedding model into the image so the app never touches
#    the network at runtime (HF_HUB_OFFLINE=1 below). fastembed reads
#    FASTEMBED_CACHE_PATH when no cache_dir is passed.
#    Build args:
#      HF_ENDPOINT      download mirror for slow networks, e.g.
#                       --build-arg HF_ENDPOINT=https://hf-mirror.com
#      EMBEDDING_MODEL  must match the EMBEDDING_MODEL the app runs with;
#                       changing it requires rebuilding the image
ARG HF_ENDPOINT
ARG EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
ENV FASTEMBED_CACHE_PATH=/opt/fastembed-cache
RUN HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}" \
    .venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBEDDING_MODEL}')"

# 3. Install the project itself (editable), then copy runtime static assets.
COPY app/examradar/ examradar/
RUN uv sync --frozen --no-dev
COPY app/static/ static/

ENV APP_HOST=0.0.0.0
ENV APP_PORT=18800
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL}
ENV HF_HUB_OFFLINE=1

EXPOSE 18800

CMD ["uv", "run", "--no-sync", "uvicorn", "examradar.main:app", "--host", "0.0.0.0", "--port", "18800"]
