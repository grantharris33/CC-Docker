FROM node:20-slim

# Install system dependencies including Playwright and VNC requirements
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
    # VNC and X11 dependencies
    x11vnc \
    xvfb \
    fluxbox \
    net-tools \
    supervisor \
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

# Install noVNC for web-based VNC access
RUN cd /opt && \
    git clone --depth 1 https://github.com/novnc/noVNC.git && \
    cd noVNC && \
    git clone --depth 1 https://github.com/novnc/websockify.git && \
    cd websockify && \
    python3 -m venv venv && \
    venv/bin/pip install -e .

# Install uv for Python dependency management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy wrapper code
COPY wrapper/ /opt/wrapper/

# Install wrapper dependencies using uv (creates .venv in /opt/wrapper/)
WORKDIR /opt/wrapper
RUN uv sync --no-dev --no-install-project
ENV VIRTUAL_ENV=/opt/wrapper/.venv
ENV PATH="/opt/wrapper/.venv/bin:$PATH"
WORKDIR /

# Copy CC-Docker MCP server
COPY mcp-server/ /opt/cc-docker-mcp/
RUN cd /opt/cc-docker-mcp && npm install --production

# Create skills directory and copy skills
RUN mkdir -p /opt/cc-docker/skills
COPY skills/ /opt/cc-docker/skills/

# Copy supervisord configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create non-root user for security (Claude won't run with --dangerously-skip-permissions as root)
RUN useradd -m -s /bin/bash claude

# Create workspace and shared directories
RUN mkdir -p /workspace /shared && chown claude:claude /workspace /shared

# Create .claude directory for mounted config
RUN mkdir -p /home/claude/.claude && chown -R claude:claude /home/claude

# Set proper ownership for opt directories that need claude access
RUN chown -R claude:claude /opt/cc-docker-mcp /opt/cc-docker /opt/noVNC

# Create directories for supervisor logs
RUN mkdir -p /tmp && chown claude:claude /tmp

# Expose VNC port
EXPOSE 5900

# Set working directory
WORKDIR /workspace

# Pre-authenticated Claude config will be mounted at runtime
# /home/claude/.claude/ -> mounted volume with OAuth token

# Entry point: Start supervisord which manages Xvfb, fluxbox, x11vnc, and wrapper
ENTRYPOINT ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
