# Multi-stage build for the RegDelta API.
# Stage 1 (builder) installs dependencies into a venv; the runtime stage copies
# only that venv so ML wheels (torch/sentence-transformers) don't bloat layers.
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy metadata first for layer caching, then install.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY . .

EXPOSE 8000
# Migrations are applied by `make migrate`; the container just serves.
# run_api.py sets the event-loop policy before uvicorn creates its loop
# (required on Windows, harmless here) — one entrypoint everywhere.
CMD ["python", "run_api.py"]
