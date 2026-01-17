FROM python:3.12-slim

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
ENV PATH="/root/.local/bin:$PATH"

# Copy pyproject.toml for dependency installation
COPY pyproject.toml .

# Create virtual environment and install dependencies from pyproject.toml
RUN uv venv .venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv pip install --requirement pyproject.toml

# Copy application code
COPY app/ ./app/

# Copy static files
COPY static/ ./static/

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
