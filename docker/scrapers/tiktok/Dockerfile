ARG BASE_IMAGE=agflow-scraper-base:latest
FROM ${BASE_IMAGE}

COPY tiktok/ /app/tiktok/

ENTRYPOINT ["python", "-m", "tiktok.entrypoint"]
