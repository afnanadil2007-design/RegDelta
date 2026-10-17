# The API image: CPython 3.11 and exactly the dependency set in
# requirements.lock.
#
# One stage on purpose. Every dependency installs from a prebuilt wheel, so a
# build stage would leave no compiler behind, and copying a finished
# environment into a second stage does not make it smaller: the image is
# large because torch and the other ML wheels are, wherever they are copied.
FROM python:3.11.16-slim-bookworm

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# --no-deps installs the locked list and resolves nothing else; `pip check`
# then fails the build if that list is not self-consistent. torch is the CPU
# build, which only the PyTorch index serves.
COPY requirements.lock ./
RUN pip install --no-deps -r requirements.lock \
        --extra-index-url https://download.pytorch.org/whl/cpu \
    && pip check

# The application runs from source (it is not installed): the prompts under
# app/ai/prompts are data files that a wheel built from pyproject.toml would
# leave out.
COPY alembic.ini run_api.py ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000
# Migrations are applied from the host (`make db`); the container only serves.
CMD ["python", "run_api.py"]
