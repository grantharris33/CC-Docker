#!/bin/bash
# Setup script for CC-Docker

set -e

echo "Setting up CC-Docker..."

# Create directories
mkdir -p data configs

# Copy example env file if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env file - please update with your settings"
fi

# Build container image
echo "Building container image..."
docker build -t cc-docker-container:latest -f container/Dockerfile .

# Build and start services
echo "Building and starting services..."
docker-compose build
docker-compose up -d

echo "Setup complete!"
echo ""
echo "Services:"
echo "  - Gateway API: http://localhost:8000"
echo "  - API Docs:    http://localhost:8000/docs"
echo "  - MinIO Console: http://localhost:9001"
echo ""
echo "To view logs: docker-compose logs -f"
