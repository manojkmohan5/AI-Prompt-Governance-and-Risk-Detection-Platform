FROM python:3.12-slim

# curl is used by the healthcheck. Unpinned: Debian's apt snapshot for this
# base image rotates its package versions, so a pinned one would eventually
# 404 and break rebuilds.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# No models here: everything that reads text for confidential content runs in
# the detection service, so this image carries no PyTorch.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
