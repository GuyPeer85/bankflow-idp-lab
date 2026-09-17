FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN useradd \
    --uid 10001 \
    --create-home \
    appuser

WORKDIR /app

COPY --chown=appuser:appuser app.py /app/app.py

USER 10001

EXPOSE 8080

CMD ["python", "app.py"]