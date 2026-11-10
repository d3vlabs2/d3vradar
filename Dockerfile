FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RADAR_DATA=/data
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home radar && mkdir /data && chown radar:radar /data
COPY --chown=radar:radar radar ./radar
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "radar.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
