# Playwright base includes Chromium + system deps (YouTube mapping fallback).
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/app ./app
COPY web ./web
RUN mkdir -p /app/data
ENV PYTHONPATH=/app
EXPOSE 8100
# Render injects $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8100}"]
