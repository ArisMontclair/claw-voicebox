FROM python:3.12-slim

# System deps for audio + whisper + ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    portaudio19-dev \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline.py .
COPY web_server.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8080

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["./entrypoint.sh"]
