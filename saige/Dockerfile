# Dockerfile for HITL-AG-AGENT-BACKEND
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy full Saige package (app/, graph/, shims, …). Do not COPY *.py only.
COPY . .

# Expose port (FastAPI default)
EXPOSE 8000

# Health: Cloud Run / load balancer
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

# Entrypoint via root compatibility shim: api.py → app.api:app
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

