ARG BASE_IMAGE=agflow-scraper-base:latest
FROM ${BASE_IMAGE}

COPY instagram/ /app/instagram/

ENTRYPOINT ["python", "-m", "instagram.entrypoint"]
