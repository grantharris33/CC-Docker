---
name: delegate-task
description: |
  Delegate a task to a child Docker container session. Use when you need to:
  - Parallelize work across multiple isolated instances
  - Isolate a complex subtask that needs its own context
  - Run long-running operations without blocking
  - Process multiple files/directories concurrently
  Keywords: spawn, child, parallel, delegate, fork, worker
allowed-tools:
  - mcp__cc-docker__spawn_child
  - mcp__cc-docker__get_child_output
  - mcp__cc-docker__get_child_result
  - mcp__cc-docker__list_children
  - Read
  - Write
user-invocable: true
---

# Delegate Task

When delegating a task to a child Docker container session:

## Decision Criteria

**Use Docker child (this skill)** when:
- Task needs isolation (separate workspace, fresh context)
- Task is long-running (>30 seconds)
- Task can run in parallel with other work
- Task involves heavy computation or many file operations

**Use built-in Task tool instead** when:
- Quick code exploration or file search
- Simple questions that need codebase context
- Tasks that benefit from shared parent context

## Usage

Use the CC-Docker MCP `spawn_child` tool:

```
spawn_child(
  prompt="Your detailed task description",
  context={"key": "value"},  # Optional context data
  stream_output=true          # Whether to stream output back
)
```

## Best Practices

- Break large tasks into smaller, focused subtasks
- Each child should have a single, clear objective
- Provide enough context but avoid overwhelming the child
- Use streaming for long-running tasks to monitor progress
- Always check child results before proceeding
- Clean up completed children to free resources
