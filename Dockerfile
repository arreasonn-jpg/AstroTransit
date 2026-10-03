# syntax=docker/dockerfile:1.7

# ============================================================
# Stage 1: builder
# Bilimsel bagimliliklar burada wheel olarak hazirlanir.
# Derleme araclari (gcc, gfortran) runtime imajina tasinmaz.
# ============================================================
FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gfortran \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY envs/requirements-docker.lock /tmp/requirements.lock

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip wheel --wheel-dir /wheels \
        -r /tmp/requirements.lock \
        setuptools wheel

# ============================================================
# Stage 2: runtime
# Slim, non-root, tini init. Wheel'ler BuildKit bind mount ile
# gecici olarak baglanir; hicbir katmana kopyalanmaz.
# ============================================================
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="AstroTransit" \
      org.opencontainers.image.description="TESS transit detection and candidate characterization platform" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/arreasonn-jpg/AstroTransit"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 astrotransit \
    && useradd --system --uid 1000 --gid astrotransit \
        --create-home --shell /bin/bash astrotransit

WORKDIR /app

# BuildKit bind mount: wheel'ler ve requirements-docker.lock hicbir
# layer'a kopyalanmaz, RUN biter bitmez kaybolur.
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    --mount=type=bind,from=builder,source=/tmp/requirements.lock,target=/tmp/requirements.lock \
    python -m pip install --no-compile --no-index --find-links=/wheels \
        -r /tmp/requirements.lock \
    && python -m pip install --no-compile --no-index --find-links=/wheels \
        setuptools wheel \
    && find /usr/local/lib/python3.11/site-packages \
        -type d -name "tests" -prune -exec rm -rf {} + \
    && find /usr/local/lib/python3.11/site-packages \
        -type d -name "__pycache__" -prune -exec rm -rf {} + \
    && find /usr/local/lib/python3.11/site-packages \
        -type f -name "*.pyc" -delete

COPY pyproject.toml README.md LICENSE CITATION.cff ./
COPY astrotransit ./astrotransit
COPY cli ./cli
COPY dashboard ./dashboard

RUN python -m pip install --no-deps --no-build-isolation . \
    && chown -R astrotransit:astrotransit /app

USER astrotransit

ENTRYPOINT ["/usr/bin/tini", "--", "astrotransit"]
CMD ["--help"]
