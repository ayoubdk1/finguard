FROM python:3.15-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /build

COPY requirements.txt requirements-auth.txt ./
RUN pip install --no-cache-dir --upgrade pip &&     pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt -r requirements-auth.txt


FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl && rm -rf /wheels /usr/local/lib/python3.13/site-packages/pip* /usr/local/lib/python3.13/site-packages/setuptools* /usr/local/lib/python3.13/ensurepip

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY models ./models
COPY scripts ./scripts

RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
