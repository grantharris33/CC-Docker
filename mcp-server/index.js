#!/usr/bin/env node
/**
 * CC-Docker MCP Server
 *
 * Provides inter-session communication capabilities for Claude Code instances
 * running in Docker containers.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import Redis from "ioredis";

// Configuration from environment
const SESSION_ID = process.env.SESSION_ID;
const REDIS_URL = process.env.REDIS_URL || "redis://redis:6379";
const GATEWAY_URL = process.env.GATEWAY_URL || "http://gateway:8000";

if (!SESSION_ID) {
  console.error("SESSION_ID environment variable is required");
  process.exit(1);
}

// Redis client
let redis = null;
let pubsub = null;

async function getRedis() {
  if (!redis) {
    redis = new Redis(REDIS_URL);
    redis.on("error", (err) => console.error("Redis error:", err));
  }
  return redis;
}

async function getPubSub() {
  if (!pubsub) {
    pubsub = new Redis(REDIS_URL);
    pubsub.on("error", (err) => console.error("Redis pubsub error:", err));
  }
  return pubsub;
}

// Gateway API helper
async function gatewayRequest(endpoint, method = "GET", body = null) {
  const url = `${GATEWAY_URL}${endpoint}`;
  const options = {
    method,
    headers: {
      "Content-Type": "application/json",
      // Use internal service auth - no JWT needed for internal calls
      "X-Internal-Service": "cc-docker-mcp",
      "X-Session-ID": SESSION_ID,
    },
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(url, options);

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Gateway request failed: ${response.status} - ${error}`);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

// Tool definitions
const TOOLS = [
  {
    name: "spawn_child",
    description:
      "Spawn a new child Claude Code session in a Docker container. Returns the child session ID.",
    inputSchema: {
      type: "object",
      properties: {
        prompt: {
          type: "string",
          description: "Initial prompt for the child session",
        },
        context: {
          type: "object",
          description: "Optional context data to pass to child",
        },
        task_type: {
          type: "string",
          description: "Optional task categorization (e.g., 'code-review', 'research')",
        },
        stream_output: {
          type: "boolean",
          description: "Whether to stream output back (default: true)",
          default: true,
        },
        timeout_seconds: {
          type: "number",
          description: "Child session timeout in seconds (default: 1800)",
          default: 1800,
        },
      },
      required: ["prompt"],
    },
  },
  {
    name: "send_to_child",
    description: "Send a follow-up prompt to an existing child session.",
    inputSchema: {
      type: "object",
      properties: {
        child_session_id: {
          type: "string",
          description: "ID of the child session",
        },
        prompt: {
          type: "string",
          description: "Prompt to send to the child",
        },
        wait_for_result: {
          type: "boolean",
          description: "Whether to wait for the child to complete",
          default: false,
        },
      },
      required: ["child_session_id", "prompt"],
    },
  },
  {
    name: "get_child_output",
    description:
      "Get the current streaming output from a child session.",
    inputSchema: {
      type: "object",
      properties: {
        child_session_id: {
          type: "string",
          description: "ID of the child session",
        },
        since_timestamp: {
          type: "string",
          description: "Get output since this ISO timestamp",
        },
        max_lines: {
          type: "number",
          description: "Maximum lines to return (default: 100)",
          default: 100,
        },
      },
      required: ["child_session_id"],
    },
  },
  {
    name: "get_child_result",
    description:
      "Get the final result from a child session. Can optionally wait for completion.",
    inputSchema: {
      type: "object",
      properties: {
        child_session_id: {
          type: "string",
          description: "ID of the child session",
        },
        wait: {
          type: "boolean",
          description: "Wait for child to complete if still running",
          default: false,
        },
        timeout_seconds: {
          type: "number",
          description: "Timeout for waiting (default: 300)",
          default: 300,
        },
      },
      required: ["child_session_id"],
    },
  },
  {
    name: "list_children",
    description: "List all child sessions spawned by this session.",
    inputSchema: {
      type: "object",
      properties: {
        status_filter: {
          type: "array",
          items: { type: "string" },
          description: "Filter by status (e.g., ['running', 'idle'])",
        },
        include_completed: {
          type: "boolean",
          description: "Include completed children (default: true)",
          default: true,
        },
      },
    },
  },
  {
    name: "stop_child",
    description: "Stop a running child session.",
    inputSchema: {
      type: "object",
      properties: {
        child_session_id: {
          type: "string",
          description: "ID of the child session to stop",
        },
        force: {
          type: "boolean",
          description: "Force immediate termination",
          default: false,
        },
      },
      required: ["child_session_id"],
    },
  },
  {
    name: "interrupt_child",
    description:
      "Send an interrupt/redirect message to a child session. Use this to change what the child is working on mid-execution.",
    inputSchema: {
      type: "object",
      properties: {
        child_session_id: {
          type: "string",
          description: "ID of the child session to interrupt",
        },
        message: {
          type: "string",
          description:
            "The redirect message to send to the child. This will be injected as a high-priority prompt.",
        },
        interrupt_type: {
          type: "string",
          enum: ["redirect", "stop", "pause"],
          description:
            "Type of interrupt: 'redirect' (change task), 'stop' (end session), 'pause' (pause execution)",
          default: "redirect",
        },
        priority: {
          type: "string",
          enum: ["normal", "high", "critical"],
          description: "Priority level of the interrupt",
          default: "high",
        },
      },
      required: ["child_session_id", "message"],
    },
  },
  {
    name: "get_child_workspace_path",
    description:
      "Get the path to a child's workspace. The child workspace is mounted under this session's workspace at /workspace/children/<child_session_id>/",
    inputSchema: {
      type: "object",
      properties: {
        child_session_id: {
          type: "string",
          description: "ID of the child session",
        },
      },
      required: ["child_session_id"],
    },
  },
  {
    name: "get_parent_context",
    description:
      "Get context or data from the parent session (only available for child sessions).",
    inputSchema: {
      type: "object",
      properties: {
        key: {
          type: "string",
          description: "Specific context key to retrieve",
        },
      },
    },
  },
  {
    name: "notify_user",
    description:
      "Send a notification to the user via Discord. This is fire-and-forget - the message is posted and this call returns immediately. Use this when you want to inform the user about progress, completion, or important events without waiting for a response.",
    inputSchema: {
      type: "object",
      properties: {
        message: {
          type: "string",
          description: "The notification message to send (max 2000 characters)",
        },
        priority: {
          type: "string",
          enum: ["normal", "urgent"],
          description: "Priority level: 'normal' or 'urgent' (default: normal)",
          default: "normal",
        },
        summary: {
          type: "string",
          description: "Optional summary or additional details (max 4000 characters)",
        },
      },
      required: ["message"],
    },
  },
  {
    name: "ask_user",
    description:
      "Ask the user a question via Discord and BLOCK waiting for their response. This will post the question in Discord and wait up to the timeout period for the user to reply. The question will retry multiple times if no response is received. Use this when you need user input, clarification, or approval before proceeding.",
    inputSchema: {
      type: "object",
      properties: {
        question: {
          type: "string",
          description: "The question to ask the user (max 2000 characters)",
        },
        timeout_seconds: {
          type: "number",
          description: "Timeout in seconds per attempt (default: 1800 = 30 minutes)",
          default: 1800,
          minimum: 60,
          maximum: 7200,
        },
        max_attempts: {
          type: "number",
          description: "Maximum retry attempts (default: 3)",
          default: 3,
          minimum: 1,
          maximum: 5,
        },
        priority: {
          type: "string",
          enum: ["normal", "urgent"],
          description: "Priority level: 'normal' or 'urgent' (default: normal)",
          default: "normal",
        },
        options: {
          type: "array",
          items: { type: "string" },
          description: "Optional list of quick reply options",
        },
      },
      required: ["question"],
    },
  },
];

// Tool implementations
async function spawnChild(args) {
  const { prompt, context, task_type, stream_output = true, timeout_seconds = 1800 } =
    args;

  try {
    // Call gateway to spawn child session
    const result = await gatewayRequest(
      `/api/v1/sessions/${SESSION_ID}/spawn`,
      "POST",
      {
        prompt,
        context,
        task_type,
        config: {
          timeout_seconds,
          stream_output,
        },
      }
    );

    // If stream_output, start listening for output
    if (stream_output) {
      const redis = await getRedis();
      // Store child info for later retrieval
      await redis.hset(
        `session:${SESSION_ID}:children`,
        result.child_session_id,
        JSON.stringify({
          created_at: new Date().toISOString(),
          task_type,
          status: result.status,
        })
      );
    }

    // Send the initial prompt to the child
    const redisClient = await getRedis();
    await redisClient.rpush(
      `session:${result.child_session_id}:input`,
      JSON.stringify({ prompt })
    );

    return {
      child_session_id: result.child_session_id,
      status: result.status,
      message: `Child session spawned successfully. Use get_child_output or get_child_result to monitor progress.`,
    };
  } catch (error) {
    return {
      error: true,
      message: `Failed to spawn child: ${error.message}`,
    };
  }
}

async function sendToChild(args) {
  const { child_session_id, prompt, wait_for_result = false } = args;

  try {
    const redis = await getRedis();

    // Verify child exists and belongs to this parent
    const childInfo = await redis.hget(
      `session:${SESSION_ID}:children`,
      child_session_id
    );
    if (!childInfo) {
      return {
        error: true,
        message: `Child session ${child_session_id} not found or does not belong to this session`,
      };
    }

    // Send prompt to child's input queue
    await redis.rpush(
      `session:${child_session_id}:input`,
      JSON.stringify({ prompt })
    );

    const response = {
      message_id: `msg-${Date.now()}`,
      status: "queued",
    };

    if (wait_for_result) {
      // Wait for result
      const result = await waitForChildResult(child_session_id, 300);
      response.result = result;
    }

    return response;
  } catch (error) {
    return {
      error: true,
      message: `Failed to send to child: ${error.message}`,
    };
  }
}

async function getChildOutput(args) {
  const { child_session_id, since_timestamp, max_lines = 100 } = args;

  try {
    const redis = await getRedis();

    // Get buffered output from Redis
    const outputKey = `session:${child_session_id}:output_buffer`;
    const outputs = await redis.lrange(outputKey, -max_lines, -1);

    // Filter by timestamp if provided
    let filteredOutputs = outputs.map((o) => JSON.parse(o));
    if (since_timestamp) {
      const sinceTime = new Date(since_timestamp).getTime();
      filteredOutputs = filteredOutputs.filter(
        (o) => new Date(o.timestamp).getTime() > sinceTime
      );
    }

    // Check if child is still running
    const state = await redis.hgetall(`session:${child_session_id}:state`);
    const isComplete = state.status === "stopped" || state.status === "failed";

    return {
      output: filteredOutputs
        .map((o) => o.data?.content || o.data?.result || JSON.stringify(o.data))
        .join("\n"),
      is_complete: isComplete,
      status: state.status || "unknown",
      timestamp: new Date().toISOString(),
      line_count: filteredOutputs.length,
    };
  } catch (error) {
    return {
      error: true,
      message: `Failed to get child output: ${error.message}`,
    };
  }
}

async function waitForChildResult(childSessionId, timeoutSeconds) {
  const redis = await getRedis();
  const startTime = Date.now();
  const timeoutMs = timeoutSeconds * 1000;

  while (Date.now() - startTime < timeoutMs) {
    const state = await redis.hgetall(`session:${childSessionId}:state`);

    if (state.status === "idle" || state.status === "stopped") {
      // Get the result
      const resultKey = `session:${childSessionId}:result`;
      const result = await redis.get(resultKey);
      return result ? JSON.parse(result) : { status: state.status };
    }

    if (state.status === "failed") {
      return { status: "failed", error: state.error || "Child session failed" };
    }

    // Wait before checking again
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  return { status: "timeout", message: "Timed out waiting for child result" };
}

async function getChildResult(args) {
  const { child_session_id, wait = false, timeout_seconds = 300 } = args;

  try {
    const redis = await getRedis();

    // Check current state
    const state = await redis.hgetall(`session:${child_session_id}:state`);

    if (!state.status) {
      return {
        error: true,
        message: `Child session ${child_session_id} not found`,
      };
    }

    // If still running and wait is true, wait for completion
    if (state.status === "running" && wait) {
      return await waitForChildResult(child_session_id, timeout_seconds);
    }

    // Get the result if available
    const resultKey = `session:${child_session_id}:result`;
    const result = await redis.get(resultKey);

    if (result) {
      const parsedResult = JSON.parse(result);
      return {
        status: "completed",
        result: parsedResult.result,
        usage: parsedResult.usage,
      };
    }

    return {
      status: state.status,
      message:
        state.status === "running"
          ? "Child is still running. Use wait=true to wait for completion."
          : "No result available",
    };
  } catch (error) {
    return {
      error: true,
      message: `Failed to get child result: ${error.message}`,
    };
  }
}

async function listChildren(args) {
  const { status_filter, include_completed = true } = args || {};

  try {
    const redis = await getRedis();

    // Get all children from hash
    const children = await redis.hgetall(`session:${SESSION_ID}:children`);

    const result = [];
    for (const [childId, infoJson] of Object.entries(children)) {
      const info = JSON.parse(infoJson);

      // Get current state
      const state = await redis.hgetall(`session:${childId}:state`);
      const status = state.status || "unknown";

      // Apply filters
      if (status_filter && !status_filter.includes(status)) {
        continue;
      }
      if (
        !include_completed &&
        (status === "stopped" || status === "failed")
      ) {
        continue;
      }

      result.push({
        session_id: childId,
        status,
        created_at: info.created_at,
        task_type: info.task_type,
      });
    }

    return {
      children: result,
      total: result.length,
    };
  } catch (error) {
    return {
      error: true,
      message: `Failed to list children: ${error.message}`,
    };
  }
}

async function stopChild(args) {
  const { child_session_id, force = false } = args;

  try {
    // Call gateway to stop session
    const result = await gatewayRequest(
      `/api/v1/sessions/${child_session_id}/stop`,
      "POST",
      { force }
    );

    // Update local tracking
    const redis = await getRedis();
    const childInfo = await redis.hget(
      `session:${SESSION_ID}:children`,
      child_session_id
    );
    if (childInfo) {
      const info = JSON.parse(childInfo);
      info.status = "stopped";
      info.stopped_at = new Date().toISOString();
      await redis.hset(
        `session:${SESSION_ID}:children`,
        child_session_id,
        JSON.stringify(info)
      );
    }

    return {
      success: true,
      final_status: "stopped",
    };
  } catch (error) {
    return {
      error: true,
      message: `Failed to stop child: ${error.message}`,
    };
  }
}

async function interruptChild(args) {
  const {
    child_session_id,
    message,
    interrupt_type = "redirect",
    priority = "high",
  } = args;

  try {
    const redis = await getRedis();

    // Verify child exists and belongs to this parent
    const childInfo = await redis.hget(
      `session:${SESSION_ID}:children`,
      child_session_id
    );
    if (!childInfo) {
      return {
        error: true,
        message: `Child session ${child_session_id} not found or does not belong to this session`,
      };
    }

    // Call gateway to send interrupt
    const result = await gatewayRequest(
      `/api/v1/sessions/${child_session_id}/interrupt`,
      "POST",
      {
        type: interrupt_type,
        message: message,
        priority: priority,
      }
    );

    return {
      success: true,
      interrupt_type: interrupt_type,
      timestamp: result.timestamp,
      message: `Interrupt sent to child session ${child_session_id}. The child will process this message after completing its current turn.`,
    };
  } catch (error) {
    return {
      error: true,
      message: `Failed to interrupt child: ${error.message}`,
    };
  }
}

async function getChildWorkspacePath(args) {
  const { child_session_id } = args;

  try {
    const redis = await getRedis();

    // Verify child exists and belongs to this parent
    const childInfo = await redis.hget(
      `session:${SESSION_ID}:children`,
      child_session_id
    );
    if (!childInfo) {
      return {
        error: true,
        message: `Child session ${child_session_id} not found or does not belong to this session`,
      };
    }

    // Child workspace is mounted under parent's workspace
    const childWorkspacePath = `/workspace/children/${child_session_id}`;

    return {
      child_session_id: child_session_id,
      workspace_path: childWorkspacePath,
      description: `The child's workspace is accessible at ${childWorkspacePath}. Any files created by the child will appear here.`,
    };
  } catch (error) {
    return {
      error: true,
      message: `Failed to get child workspace path: ${error.message}`,
    };
  }
}

async function getParentContext(args) {
  const { key } = args || {};

  const parentSessionId = process.env.PARENT_SESSION_ID;
  if (!parentSessionId) {
    return {
      error: true,
      message: "This is a root session - no parent available",
    };
  }

  try {
    const redis = await getRedis();

    if (key) {
      // Get specific context key
      const value = await redis.hget(
        `session:${parentSessionId}:context`,
        key
      );
      return { key, value: value ? JSON.parse(value) : null };
    } else {
      // Get all context
      const context = await redis.hgetall(`session:${parentSessionId}:context`);
      const parsed = {};
      for (const [k, v] of Object.entries(context)) {
        parsed[k] = JSON.parse(v);
      }
      return { context: parsed };
    }
  } catch (error) {
    return {
      error: true,
      message: `Failed to get parent context: ${error.message}`,
    };
  }
}

// Discord notification tool
async function notifyUser(args) {
  const { message, priority = "normal", summary } = args;

  try {
    const result = await gatewayRequest(
      "/api/v1/discord/notify",
      "POST",
      {
        session_id: SESSION_ID,
        message,
        priority,
        summary,
      }
    );

    return {
      success: true,
      interaction_id: result.interaction_id,
      message: "Notification sent to user via Discord",
    };
  } catch (error) {
    return {
      error: true,
      message: `Failed to send notification: ${error.message}`,
    };
  }
}

// Discord ask question tool
async function askUser(args) {
  const {
    question,
    timeout_seconds = 1800,
    max_attempts = 3,
    priority = "normal",
    options,
  } = args;

  try {
    const result = await gatewayRequest(
      "/api/v1/discord/ask",
      "POST",
      {
        session_id: SESSION_ID,
        question,
        timeout_seconds,
        max_attempts,
        priority,
        options,
      }
    );

    if (result.timed_out) {
      return {
        error: true,
        timed_out: true,
        message: `Question timed out after ${max_attempts} attempts. User did not respond within the ${timeout_seconds} second timeout period for each attempt.`,
        interaction_id: result.interaction_id,
      };
    }

    return {
      success: true,
      response: result.response,
      interaction_id: result.interaction_id,
      message: `User responded: ${result.response}`,
    };
  } catch (error) {
    return {
      error: true,
      message: `Failed to ask question: ${error.message}`,
    };
  }
}

// Tool handler
async function handleTool(name, args) {
  switch (name) {
    case "spawn_child":
      return await spawnChild(args);
    case "send_to_child":
      return await sendToChild(args);
    case "get_child_output":
      return await getChildOutput(args);
    case "get_child_result":
      return await getChildResult(args);
    case "list_children":
      return await listChildren(args);
    case "stop_child":
      return await stopChild(args);
    case "interrupt_child":
      return await interruptChild(args);
    case "get_child_workspace_path":
      return await getChildWorkspacePath(args);
    case "get_parent_context":
      return await getParentContext(args);
    case "notify_user":
      return await notifyUser(args);
    case "ask_user":
      return await askUser(args);
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

// Create MCP server
const server = new Server(
  {
    name: "cc-docker-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Register handlers
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: TOOLS };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    const result = await handleTool(name, args || {});
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ error: true, message: error.message }),
        },
      ],
      isError: true,
    };
  }
});

// Start server
async function main() {
  console.error(`Starting CC-Docker MCP Server for session ${SESSION_ID}`);
  console.error(`Redis URL: ${REDIS_URL}`);
  console.error(`Gateway URL: ${GATEWAY_URL}`);

  const transport = new StdioServerTransport();
  await server.connect(transport);

  console.error("CC-Docker MCP Server running on stdio");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});

// Cleanup on exit
process.on("SIGINT", async () => {
  if (redis) await redis.quit();
  if (pubsub) await pubsub.quit();
  process.exit(0);
});

process.on("SIGTERM", async () => {
  if (redis) await redis.quit();
  if (pubsub) await pubsub.quit();
  process.exit(0);
});
