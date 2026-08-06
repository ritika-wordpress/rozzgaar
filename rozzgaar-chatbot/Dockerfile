FROM python:3.11-slim

WORKDIR /app

# System deps: only certs/curl needed (no ffmpeg - tts libs are pure HTTP/python)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY app ./app
COPY static ./static

# Writable dir for the knowledge base cache (data/kb.joblib is gitignored -
# it gets rebuilt on first /ingest/refresh call, or you can COPY a prebuilt
# one in here if you have one and want to skip that step)
RUN mkdir -p /app/data

# Never bake secrets into the image - all config comes from env vars
# injected by the AWS service (App Runner / ECS task def / EB env), same
# names as .env.example.
ENV DATA_DIR=/app/data
ENV PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Shell form so $PORT expands - AWS App Runner/ECS often inject PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
