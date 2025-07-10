# Use official Python runtime as base image
# Use official Python runtime as base image
FROM python:3.10-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create appuser and set permissions for /app and /data
RUN useradd -ms /bin/bash appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser

WORKDIR /app

# Copy application code
COPY . .


# Expose port from settings
EXPOSE 80

RUN pip install httpx

# Command to run the application
CMD ["python", "/app/src/server/main.py", "--host", "0.0.0.0", "--port", "80"]