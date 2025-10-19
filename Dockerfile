FROM python:3.11-slim

# Install pg_dump & curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Create runtime dirs
RUN mkdir -p /app/logs /app/backups /app/data && chmod -R 777 /app/logs /app/backups /app/data

COPY . /app

HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
