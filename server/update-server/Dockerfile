FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PAN4DEX_UPDATE_DATA_DIR=/data \
    PAN4DEX_UPDATE_PORT=23011

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py storage.py ./
COPY templates ./templates
COPY static ./static

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 23011

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:23011/healthz', timeout=3)"

CMD ["python", "app.py"]
