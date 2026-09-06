# Use official Python runtime as base image
FROM python:3.11-slim

# Install system dependencies (FFmpeg & build essentials for PyNaCl)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose HTTP port for Render web service health check
EXPOSE 8080

# Run the bot
CMD ["python", "bot.py"]
