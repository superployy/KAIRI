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

COPY main.py .

# cookies.txt is optional but strongly recommended to avoid YouTube bot detection.
# To use: export cookies from Chrome/Firefox while logged into YouTube using the
# "Get cookies.txt LOCALLY" extension, save as cookies.txt in your repo root,
# then uncomment the line below and redeploy.
COPY cookies.txt .

CMD ["python", "main.py"]
