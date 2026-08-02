# Aletheia API Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies directly
RUN pip install --no-cache-dir \
    fastapi==0.139.0 \
    uvicorn==0.51.0 \
    openai==2.45.0 \
    psycopg==3.3.4 \
    pgvector==0.5.0 \
    mcp==1.28.1 \
    anthropic==0.116.0 \
    ragas==0.4.3

# Patch ragas to use new langchain_google_vertexai import location
COPY scripts/patch_ragas.py /tmp/patch_ragas.py
RUN python /tmp/patch_ragas.py \
    ragas==0.4.3

# Copy application code
COPY app/ ./app/
COPY db/ ./db/
COPY scripts/ ./scripts/

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]