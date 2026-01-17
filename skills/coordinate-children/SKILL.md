---
name: coordinate-children
description: |
  Coordinate multiple Docker container child sessions working on related tasks.
  Use when parallelizing work across multiple children or when tasks have dependencies.
  Keywords: parallel, concurrent, fan-out, fan-in, pipeline, orchestrate, coordinate
allowed-tools:
  - mcp__cc-docker__spawn_child
  - mcp__cc-docker__send_to_child
  - mcp__cc-docker__get_child_output
  - mcp__cc-docker__get_child_result
  - mcp__cc-docker__list_children
  - mcp__cc-docker__stop_child
  - Read
  - Write
user-invocable: true
---

# Coordinate Children

When coordinating multiple Docker container child sessions:

## Workflow

1. **Plan the work breakdown**: Identify tasks that can run in parallel
2. **Spawn children**: Create child sessions for each parallel task
3. **Monitor progress**: Track status of all children via streaming
4. **Aggregate results**: Combine results once all children complete
5. **Handle failures**: Decide how to proceed if a child fails
6. **Cleanup**: Stop any remaining children

## Patterns

### Fan-out / Fan-in
Spawn multiple children for parallel work, then aggregate:

```
# Spawn children for each file
children = []
for file in files:
    child = spawn_child(prompt=f"Analyze {file}")
    children.append(child)

# Wait for all and aggregate
results = [get_child_result(c, wait=true) for c in children]
aggregate_results(results)
```

### Pipeline
Chain children where one's output feeds the next:

```
# Stage 1: Analysis
analysis = spawn_child(prompt="Analyze the codebase")
result1 = get_child_result(analysis, wait=true)

# Stage 2: Use analysis results
implementation = spawn_child(prompt=f"Implement based on: {result1}")
result2 = get_child_result(implementation, wait=true)
```

## Resource Limits

- Maximum concurrent children: 5 (configurable)
- Maximum child depth: 3 (prevent infinite recursion)
- Child timeout: 30 minutes (configurable)
