# court-api: seekdb data service for the Dify app 「喵青天·鸡毛蒜皮法庭」.
FROM python:3.11-slim-bookworm

# Mirrors can be passed at build time, e.g. --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
# --build-arg HF_ENDPOINT=https://hf-mirror.com
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG HF_ENDPOINT=https://huggingface.co

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

# Bake the embedding model (BAAI/bge-small-zh-v1.5, ~90 MB, MIT) into the image so the service runs offline.
ENV EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5 \
    EMBEDDING_DIM=512 \
    EMBEDDING_CACHE_DIR=/models
RUN HF_ENDPOINT="${HF_ENDPOINT}" python -c "from fastembed import TextEmbedding; m = TextEmbedding('${EMBEDDING_MODEL}', cache_dir='${EMBEDDING_CACHE_DIR}'); print(len(next(iter(m.embed(['喵'])))))"

COPY app ./app
COPY seed ./seed

ENV PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=30 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
