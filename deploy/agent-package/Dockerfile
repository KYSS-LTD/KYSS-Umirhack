FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -m -s /usr/sbin/nologin appuser \
    && mkdir -p /agent-data \
    && chown -R appuser:appgroup /agent-data /app

RUN pip install --no-cache-dir httpx==0.27.2 pynacl==1.5.0

COPY agent.py /app/agent.py

USER appuser

CMD ["python", "/app/agent.py"]
