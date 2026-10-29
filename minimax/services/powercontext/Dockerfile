# PowerContext Server，从 PyPI 发布包构建（官方没有发布镜像）。任务状态保存在默认的 SQLite 存储里（/data 数据卷）。
FROM python:3.11-slim-bookworm

ARG POWERCONTEXT_VERSION=1.4.1
ARG PIP_INDEX_URL=https://pypi.org/simple

RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" "powercontext[cli,server]==${POWERCONTEXT_VERSION}" \
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

HEALTHCHECK --interval=5s --timeout=5s --start-period=60s --retries=24 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]

ENTRYPOINT ["powercontext"]
CMD ["server", "run"]
