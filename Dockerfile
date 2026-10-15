FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 5000

# --preload runs db.create_all() once in the master process, so the two
# workers don't race each other creating tables on first boot.
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "--preload", "--access-logfile", "-", "app:app"]
