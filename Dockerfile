# The Flywheel backend (API + agents), for Hugging Face Spaces (Docker SDK).
# A Space runs the container as user 1000 and routes traffic to port 7860.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    FLYWHEEL_LLM_CACHE=0

# Compilers, in case a pinned package has no ready-made wheel for this platform.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app

# Dependencies first: this layer is rebuilt only when requirements change.
# --no-deps: the file is a complete freeze of the tested environment. pip cannot
# resolve it from scratch (the packages were installed in stages, which left a few
# versions that a resolver rejects but that work together), so it is installed exactly.
COPY --chown=user requirements.deploy.txt .
RUN pip install --user --no-deps -r requirements.deploy.txt

COPY --chown=user . .
RUN chmod +x deploy/start.sh

EXPOSE 7860
CMD ["sh", "deploy/start.sh"]
