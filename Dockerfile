FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY saige/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY saige/config.py saige/database.py saige/rag.py saige/weather.py saige/models.py saige/llm.py saige/nodes.py saige/graph.py saige/chat_history.py saige/redis_client.py saige/message_buffer.py saige/api.py saige/main.py saige/jwt_auth.py ./

CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8080}"]
