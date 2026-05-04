FROM python:3.11-slim

# ffmpeg required for yt-dlp audio extraction
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# yt-dlp releases multiple times per week to keep up with YouTube changes;
# always upgrade past the pinned version so nsig extraction stays current.
RUN pip install -U yt-dlp

COPY bot/ bot/
COPY config.yaml .

# Runtime data (SQLite DB) lives in a volume
VOLUME ["/app/data"]

CMD ["python", "-m", "bot.main"]
