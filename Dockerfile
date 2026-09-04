FROM python:3.11-slim

# Install FFmpeg and system dependencies for Discord audio streaming
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Render exposes PORT dynamically (default 8080)
EXPOSE 8080

CMD ["python", "bot.py"]
