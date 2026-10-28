# PowerContext Server built from the released PyPI package (no official image is published).
FROM python:3.11-slim-bookworm

ARG POWERCONTEXT_VERSION=1.4.1
ARG PIP_INDEX_URL=https://pypi.org/simple

RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" "powercontext[cli,server,seekdb]==${POWERCONTEXT_VERSION}" \
    && groupadd --gid 10001 powercontext \
    && useradd --uid 10001 --gid powercontext --home-dir /data --no-create-home --shell /usr/sbin/nologin powercontext \
    && mkdir -p /data && chown powercontext:powercontext /data

ENV PYTHONUNBUFFERED=1 \
    POWERCONTEXT_HOME=/data \
    POWERCONTEXT_SERVER_HTTP_HOST=0.0.0.0 \
    POWERCONTEXT_SERVER_HTTP_PORT=8000 \
    POWERCONTEXT_SERVER_ALLOW_UNAUTHENTICATED_NON_LOOPBACK=true

USER powercontext
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=600s --retries=10 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"]

ENTRYPOINT ["powercontext"]
CMD ["server", "run"]
