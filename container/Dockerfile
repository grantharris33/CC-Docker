FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Create Python virtual environment and install wrapper dependencies
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy wrapper code
COPY wrapper/ /opt/wrapper/
RUN pip install --no-cache-dir -r /opt/wrapper/requirements.txt

# Create non-root user for security (Claude won't run with --dangerously-skip-permissions as root)
RUN useradd -m -s /bin/bash claude

# Create workspace directory
RUN mkdir -p /workspace && chown claude:claude /workspace

# Create .claude directory for mounted config
RUN mkdir -p /home/claude/.claude && chown -R claude:claude /home/claude

# Switch to non-root user
USER claude

# Set working directory
WORKDIR /workspace

# Pre-authenticated Claude config will be mounted at runtime
# /home/claude/.claude/ -> mounted volume with OAuth token

# Entry point
ENTRYPOINT ["python3", "/opt/wrapper/main.py"]
