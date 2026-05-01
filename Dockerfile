FROM python:3.11-slim

# Install ffmpeg, libsodium (for PyNaCl), and nodejs (for yt-dlp JS runtime)
RUN apt update && apt install -y ffmpeg libsodium-dev nodejs && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the cookie file if it exists (see note below)
COPY cookies.txt ./

COPY main.py .

CMD ["python", "main.py"]
