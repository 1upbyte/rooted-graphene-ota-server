FROM python:3.14-slim

WORKDIR /app

# System deps for build script
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    git curl openssh-client unzip ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy repo
COPY . /app

# Ensure entrypoint is executable
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/app/docker/entrypoint.sh"]
