#!/bin/bash
# Example: Create a session with custom Claude Code configuration

# Replace with your JWT token
TOKEN="your-jwt-token"

# API endpoint
API_URL="http://localhost:8000/api/v1"

# Create a session with MCP servers and plugins configured
curl -X POST "${API_URL}/sessions" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace": {
      "type": "ephemeral",
      "id": "test-workspace"
    },
    "config": {
      "timeout_seconds": 3600,
      "max_turns": 100,
      "claude_config": {
        "mcp_servers": {
          "filesystem": {
            "command": "npx",
            "args": ["-y", "@anthropic-ai/mcp-server-filesystem"],
            "env": {
              "FILESYSTEM_ROOT": "/workspace"
            }
          }
        },
        "plugin_dirs": ["/plugins"],
        "model": "sonnet",
        "allowed_tools": ["*"],
        "custom_agents": {
          "code-reviewer": {
            "description": "Reviews code for quality",
            "prompt": "You are a senior code reviewer."
          }
        },
        "append_system_prompt": "This is running in a Docker container.",
        "skills_enabled": true,
        "verbose": false,
        "permission_mode": "bypassPermissions"
      }
    }
  }' | jq .

# Example: Create a minimal session (no custom config)
# curl -X POST "${API_URL}/sessions" \
#   -H "Authorization: Bearer ${TOKEN}" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "workspace": {"type": "ephemeral"},
#     "config": {}
#   }' | jq .
