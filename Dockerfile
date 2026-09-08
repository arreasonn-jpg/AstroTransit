FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE CITATION.cff ./
COPY envs/requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/requirements.lock
COPY . .
RUN python -m pip install --no-cache-dir --no-deps -e .

ENTRYPOINT ["astrotransit"]
CMD ["--help"]
