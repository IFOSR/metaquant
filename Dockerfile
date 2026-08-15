FROM python:3.12.11-slim

ARG UV_EXTRAS=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300 \
    PYTHONPATH="/app/src" \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.6 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --extra dev ${UV_EXTRAS}

COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY config ./config
COPY src ./src
COPY tests ./tests
COPY docs ./docs

RUN useradd --create-home --uid 10001 quant \
    && mkdir -p /app/.dagster \
    && chown -R quant:quant /app
USER quant

EXPOSE 8000

CMD ["uvicorn", "quant_platform.api.app:app", "--host", "0.0.0.0", "--port", "8000"]