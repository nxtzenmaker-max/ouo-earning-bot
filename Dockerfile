FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium and system dependencies for Playwright
RUN playwright install --with-deps chromium

# Copy application source
COPY . .

ENV NUM_WORKERS=45
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
