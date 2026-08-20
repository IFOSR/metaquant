# Sandbox execution image for factor construction.
#
# Built from the local API image (which already has Python 3.12, numpy, pandas,
# and the `quant_platform.ml` data client on PYTHONPATH), then adds PyTorch
# (CPU build) for the generated model code.
#
# Runs as an isolated container with --network=none and a read-only root
# filesystem (see DockerSandboxRunner).

FROM quant-platform-api:local

RUN uv pip install --no-cache --python /app/.venv/bin/python \
    torch --index-url https://download.pytorch.org/whl/cpu

COPY src/quant_platform/__init__.py /opt/quant_platform/__init__.py
COPY src/quant_platform/ml /opt/quant_platform/ml
ENV PYTHONPATH=/opt

WORKDIR /workspace
