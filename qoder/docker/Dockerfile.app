FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY app/pyproject.toml app/uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY app/examradar/ examradar/
COPY app/static/ static/

ENV APP_HOST=0.0.0.0
ENV APP_PORT=18800

EXPOSE 18800

CMD ["uv", "run", "uvicorn", "examradar.main:app", "--host", "0.0.0.0", "--port", "18800"]
