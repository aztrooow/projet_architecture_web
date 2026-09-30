FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
RUN useradd --uid 1000 --no-create-home cinetint && mkdir /data && chown cinetint /data

FROM base AS tests
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY tests ./tests
CMD ["pytest", "-q"]

FROM base
USER cinetint
VOLUME /data
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
