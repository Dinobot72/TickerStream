# backend/Dockerfile — Raspberry Pi 5 (aarch64) compatible
#
# Key changes vs original:
#   1. torch is installed first from the CPU-only wheel index so pip
#      doesn't try to pull the CUDA build (which has no aarch64 wheel).
#   2. PYTHONPATH stays as /app (matches the CMD import path).
#      Do NOT override it in docker-compose.yml.

FROM python:3.12.3

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend_requirements.txt
COPY model/requirements.txt   ./model_requirements.txt

# Install CPU-only torch FIRST so the CUDA-free wheel is selected on
# both aarch64 (Pi) and x86_64. Pin to a version that has aarch64 wheels.
RUN pip install --no-cache-dir torch==2.3.0 \
        --index-url https://download.pytorch.org/whl/cpu

# Install remaining backend + model dependencies.
# torch is already satisfied above so pip will skip it.
RUN pip install --no-cache-dir -r backend_requirements.txt
RUN pip install --no-cache-dir -r model_requirements.txt

# Copy source
COPY backend/ ./backend/
COPY model/   ./model/

# PYTHONPATH must be /app so "backend.app.main" resolves in CMD.
# docker-compose.yml must NOT override this.
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]