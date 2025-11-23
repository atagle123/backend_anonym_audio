FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./pyproject.toml
COPY uv.lock ./uv.lock

RUN python -m pip install --upgrade pip && \
    python -m pip install \
        "elevenlabs>=2.24.0" \
        "python-dotenv>=1.2.1" \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.30.1" \
        "websockets>=12.0" \
        "twilio>=9.0.0"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
