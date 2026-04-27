FROM python:3.12-slim

# ffmpeg requis par yt-dlp pour l'extraction audio
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY base/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Le code spécifique à chaque plateforme est ajouté par les Dockerfiles enfants.
