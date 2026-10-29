# sddctx 运行环境：Python 3.12 + PyMySQL（访问 seekdb）+ pytest（运行业务工程的测试）。
# 源码不打进镜像：docker-compose.yml 把 minimax/ 目录挂载到 /workspace，PYTHONPATH 指向其中的 sddctx/src。
FROM python:3.12-slim-bookworm

ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r /tmp/requirements.txt && rm /tmp/requirements.txt

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/workspace/sddctx/src \
    SDD_HOME=/workspace \
    HOME=/tmp

WORKDIR /workspace
ENTRYPOINT ["python", "-m", "sddctx"]
CMD ["--help"]
