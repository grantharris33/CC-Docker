---
name: child-status
description: |
  Check the status of Docker container child sessions. Use when you need to:
  - Monitor progress of running children
  - Check if children are complete
  - Debug stuck or failed sessions
  - View streaming output
  Keywords: status, monitor, progress, children, check, debug
allowed-tools:
  - mcp__cc-docker__list_children
  - mcp__cc-docker__get_child_output
  - mcp__cc-docker__get_child_result
  - mcp__cc-docker__stop_child
user-invocable: true
---

# Child Session Status

## Quick Commands

- `list_children()` - Show all your child sessions
- `get_child_output(id)` - Get latest output from a child
- `get_child_result(id, wait=false)` - Check if result is ready
- `stop_child(id)` - Terminate a child session

## Status Values

| Status | Meaning |
|--------|---------|
| `starting` | Container is being created |
| `idle` | Ready for input |
| `running` | Processing a prompt |
| `stopped` | Cleanly terminated |
| `failed` | Error occurred |

## Troubleshooting

**Child stuck in "running"**:
- Check streaming output with `get_child_output(id)`
- Consider sending follow-up prompt with `send_to_child(id, prompt)`
- As last resort, use `stop_child(id, force=true)`

**Child failed**:
- Check error details in `get_child_result(id)`
- Review container logs if available
- Spawn a new child with adjusted prompt/config
