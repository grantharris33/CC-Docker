FROM node:20-slim

# Install system dependencies including Playwright requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    ca-certificates \
    # Playwright browser dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Install MCP servers globally
RUN npm install -g \
    @modelcontextprotocol/server-filesystem \
    @executeautomation/playwright-mcp-server \
    @executeautomation/database-server \
    mcp-server-sqlite-npx

# Install Playwright browsers (Chromium only for container size)
RUN npx playwright install chromium --with-deps || true
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

# Create Python virtual environment and install wrapper dependencies
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy wrapper code
COPY wrapper/ /opt/wrapper/
RUN pip install --no-cache-dir -r /opt/wrapper/requirements.txt

# Copy CC-Docker MCP server
COPY mcp-server/ /opt/cc-docker-mcp/
RUN cd /opt/cc-docker-mcp && npm install --production

# Create skills directory and copy skills
RUN mkdir -p /opt/cc-docker/skills
COPY skills/ /opt/cc-docker/skills/

# Create non-root user for security (Claude won't run with --dangerously-skip-permissions as root)
RUN useradd -m -s /bin/bash claude

# Create workspace and shared directories
RUN mkdir -p /workspace /shared && chown claude:claude /workspace /shared

# Create .claude directory for mounted config
RUN mkdir -p /home/claude/.claude && chown -R claude:claude /home/claude

# Set proper ownership for opt directories that need claude access
RUN chown -R claude:claude /opt/cc-docker-mcp /opt/cc-docker

# Switch to non-root user
USER claude

# Set working directory
WORKDIR /workspace

# Pre-authenticated Claude config will be mounted at runtime
# /home/claude/.claude/ -> mounted volume with OAuth token

# Entry point
ENTRYPOINT ["python3", "/opt/wrapper/main.py"]
