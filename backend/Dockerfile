FROM python:3.12-slim

# libgomp1 is needed by faiss-cpu at runtime; curl is used by the healthcheck.
# Versions intentionally unpinned: Debian's apt snapshot for this base image
# rotates its available package versions, so a hardcoded version here would
# eventually 404 and break future rebuilds — low-risk enough for these two
# system utilities to accept that tradeoff.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch first: the default PyPI wheel for linux/aarch64 pulls in
# ~1.5GB of unused NVIDIA/CUDA packages (this app only ever does CPU
# inference). Installing the CPU build here means requirements-ml.txt's
# sentence-transformers (which depends on torch) below is already satisfied
# and won't pull the CUDA-bundled variant instead.
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements-ml.txt

# Fine-tune the DistilBERT classifier at build time and bake the weights into
# the image, so containers start in seconds instead of retraining (~3 min on
# CPU) on every cold start / restart. Only the governance module the training
# code actually needs is copied first, so unrelated app changes later in this
# Dockerfile don't invalidate this expensive layer.
COPY app/__init__.py app/
COPY app/governance/__init__.py app/governance/
COPY app/governance/ml_classifier.py app/governance/
RUN python -c "from app.governance import ml_classifier; ml_classifier.initialize()"

# Now copy the rest of the application.
COPY . .

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
