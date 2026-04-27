FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# uv pour installer les deps
RUN pip install --no-cache-dir uv

COPY pyproject.toml /app/
RUN uv pip install --system --no-cache .

COPY src/ /app/src/

ENV PYTHONPATH=/app/src

CMD ["uvicorn", "role_builder.main:app", "--host", "0.0.0.0", "--port", "8000"]
