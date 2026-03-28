FROM python:3.12-slim

LABEL maintainer="FranklinWH API Chaos Harness"

WORKDIR /app

# Install system dependencies:
# - iptables: for simulating firewall drop packets
# - iproute2 (tc): for simulating high-latency packet delivery
# - iputils-ping: to verify the container isn't already bricked before testing
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev iptables iproute2 iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Install testing dependencies inline
RUN pip install --no-cache-dir pytest requests httpx

# The library code is mounted dynamically at runtime via docker-compose into /app 
# so editing the local disk doesn't require rebuilding this container.
CMD ["tail", "-f", "/dev/null"]
