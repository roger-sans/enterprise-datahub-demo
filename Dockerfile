FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HUB_STATE=/app/.state
WORKDIR /app
COPY pyproject.toml ./
COPY hub ./hub
RUN python -m pip install --no-cache-dir . \
    && useradd --system --uid 10001 --no-create-home hub \
    && mkdir /app/.state \
    && chown hub:hub /app/.state
USER hub

EXPOSE 8000
CMD ["sh", "-c", "python -m hub seed --with-incident && exec python -m uvicorn hub.api:app --host 0.0.0.0 --port 8000"]
