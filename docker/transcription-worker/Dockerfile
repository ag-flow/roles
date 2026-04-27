# CPU base. Une variante CUDA (Dockerfile.cuda) sera ajoutée Phase H pour pve2 GPU.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg utilisé par faster-whisper pour les audios non WAV
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock /app/
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache .

COPY worker/ /app/worker/

ENV PYTHONPATH=/app

CMD ["python", "-m", "worker.main"]
