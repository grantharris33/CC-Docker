#!/bin/bash
# Build the Claude Code container image

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Building CC-Docker container image..."

# Copy required directories to container build context
cp -r "$PROJECT_DIR/wrapper" "$PROJECT_DIR/container/"
cp -r "$PROJECT_DIR/mcp-server" "$PROJECT_DIR/container/"
cp -r "$PROJECT_DIR/skills" "$PROJECT_DIR/container/"

# Build image
docker build \
    -t cc-docker-container:latest \
    -f "$PROJECT_DIR/container/Dockerfile" \
    "$PROJECT_DIR/container"

# Cleanup
rm -rf "$PROJECT_DIR/container/wrapper"
rm -rf "$PROJECT_DIR/container/mcp-server"
rm -rf "$PROJECT_DIR/container/skills"

echo "Container image built successfully: cc-docker-container:latest"
