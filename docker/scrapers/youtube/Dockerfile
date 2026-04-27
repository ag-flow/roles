ARG BASE_IMAGE=agflow-scraper-base:latest
FROM ${BASE_IMAGE}

COPY youtube/ /app/youtube/

ENTRYPOINT ["python", "-m", "youtube.entrypoint"]
