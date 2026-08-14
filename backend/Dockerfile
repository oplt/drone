FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG INSTALL_ML=0

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-api.txt backend/requirements-workers-ml.txt /app/backend/
RUN pip install --upgrade pip \
    && pip install -r /app/backend/requirements-api.txt \
    && if [ "$INSTALL_ML" = "1" ]; then pip install -r /app/backend/requirements-workers-ml.txt; fi

COPY backend /app/backend
COPY pyproject.toml /app/pyproject.toml

EXPOSE 8000

CMD ["uvicorn", "backend.entrypoints.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
