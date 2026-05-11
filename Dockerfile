FROM python:3.11-slim

# ffmpeg required for yt-dlp audio extraction
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ bot/

# Runtime data (SQLite DB) lives in a volume
VOLUME ["/app/data"]

CMD ["python3", "-m", "bot.main"]
