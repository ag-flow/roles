FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# curl pour le healthcheck du compose
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir uv

# Le contexte de build est la RACINE du repo (cf. .github/workflows/build-app.yml)
# pour pouvoir embarquer migrations/ qui vit hors de backend/.
COPY backend/pyproject.toml backend/uv.lock /app/
# Le package local harpocrate doit être présent avant l'install (path dependency dans pyproject.toml).
COPY backend/src/role_builder/secrets/ /app/src/role_builder/secrets/
RUN uv pip install --system --no-cache .

COPY backend/src/ /app/src/
# Bundle des migrations DB pour exécution automatique au startup
# (cf. role_builder.migrations.run_migrations appelé dans le lifespan).
COPY migrations/ /app/migrations/

ENV PYTHONPATH=/app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

CMD ["uvicorn", "role_builder.main:app", "--host", "0.0.0.0", "--port", "8000"]
