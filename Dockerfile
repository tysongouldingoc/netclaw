FROM python:3.12-slim

LABEL maintainer="NetClaw" \
      description="NetClaw AI Network Engineering Agent with DefenseClaw Integration"

WORKDIR /app

# Install system tools, Node.js, and git
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl gcc libffi-dev nodejs npm && \
    rm -rf /var/lib/apt/lists/*

# Install uv for Python package management
RUN pip install --no-cache-dir uv

# Copy application files
COPY . /app

# Set environment defaults
ENV N2N_RISK_MODE=production
ENV OPENCLAW_HOME=/root/.openclaw
ENV PYTHONPATH=/app:/app/mcp-servers/protocol-mcp

# Entrypoint default runs the interactive MCP installer wizard
CMD ["python", "scripts/mcp-installer.py", "--interactive"]
