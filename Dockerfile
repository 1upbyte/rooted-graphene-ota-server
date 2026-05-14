FROM nginx:alpine

WORKDIR /app

# Install Python and system deps for build script
RUN apk add --no-cache \
    python3 \
    py3-pip \
    git \
    curl \
    openssh \
    unzip \
    ca-certificates \
    uv

# Copy repo
COPY . /app

# Copy nginx config
COPY docker/nginx.conf /etc/nginx/nginx.conf

# Ensure entrypoint is executable
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/app/docker/entrypoint.sh"]
