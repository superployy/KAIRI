FROM python:3.11-slim

# Install ffmpeg, libsodium, and nodejs (for yt-dlp JS runtime)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsodium-dev \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Verify node is accessible (yt-dlp uses it for YouTube extraction)
RUN node --version && npm --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy cookies file — export from your browser while logged into YouTube
# If it doesn't exist, the bot will still run but YouTube may block requests
COPY cookies.txt .

COPY main.py .

CMD ["python", "main.py"]
