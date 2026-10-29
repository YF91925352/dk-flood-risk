FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as an unprivileged user. The code is copied with that user as owner, so the image works
# whatever file permissions the source checkout happens to have.
RUN useradd --create-home appuser
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser db ./db
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)" || exit 1

# One worker: the geocoder rate limit (1 request/second) is enforced per process.
# Uvicorn's access log is off because the app writes its own structured request log.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
