FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY messages.txt .

RUN useradd --create-home appuser && mkdir -p /srv/data && chown appuser /srv/data
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["uvicorn", "app.main:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]
