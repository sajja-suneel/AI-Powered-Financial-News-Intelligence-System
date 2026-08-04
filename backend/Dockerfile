# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Set working directory
WORKDIR /app

# Install system dependencies needed for compiling psycopg2 and running Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker build cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download SpaCy english model
RUN python -m spacy download en_core_web_sm

# Install Playwright browser and system dependencies for Crawl4AI
RUN playwright install chromium --with-deps

# Copy application source code
COPY . .

# Expose port 8000
EXPOSE 8000

# Command to run FastAPI server
CMD ["python", "-m", "src.main"]
