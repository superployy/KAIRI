FROM python:3.11-slim

RUN apt update && apt install -y ffmpeg libffi-dev openssl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pynacl==1.5.0   # Force install

COPY main.py .

CMD ["python", "main.py"]
