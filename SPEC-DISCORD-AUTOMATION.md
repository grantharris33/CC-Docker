# Discord-Driven Automated Browser Tasks - Specification

**Status**: APPROVED - Ready for Implementation
**Date**: 2026-01-17
**Last Updated**: 2026-01-17

## Overview

This specification defines the architecture for running scheduled, automated Claude Code instances that perform browser-based tasks (ticket price checking, news digests, web monitoring, etc.) with Discord as the primary control and monitoring interface.

## Goals

1. **Scheduled Automation**: Run browser tasks on schedules (daily, hourly, etc.)
2. **Discord Control**: Start, stop, monitor tasks via Discord slash commands
3. **Per-Session Channels**: Each task session gets its own Discord channel for isolation
4. **Human-in-the-Loop**: Handle captchas, MFA, errors via Discord notifications + VNC fallback
5. **Comprehensive Logging**: Store all task runs, outputs, errors in database
6. **On-Demand Execution**: Manually trigger scheduled tasks via slash commands

## Architecture Decisions (APPROVED)

Based on user feedback, the following architecture decisions have been finalized:

### 1. Discord Channel Structure ✅
**Decision**: Hybrid Model (Persistent Channels + Threads)
- One persistent channel per task type (e.g., `#ticket-checker`)
- Each task run creates a thread within that channel
- Threads named: `Run 2026-01-17 15:30 - Running/Complete/Failed`
- Clean organization with full historical context

### 2. Channel Organization ✅
**Decision**: Categories by Task Type AND Status
- Top-level categories organized by task type (Ticket Monitoring, News Digests, Web Monitoring)
- Use Discord thread states/labels to indicate status (running, complete, failed)
- Example structure:
  ```
  📁 Ticket Price Monitoring
    #flights-to-hawaii (threads: 5 complete, 1 running)
    #concerts-beyonce (threads: 12 complete)
  📁 News Digests
    #daily-tech-news (threads: 30 complete)
  📁 Web Monitoring
    #competitor-prices (threads: 8 complete, 2 failed)
  ```

### 3. Task Scheduling ✅
**Decision**: Database + APScheduler
- All schedules stored in PostgreSQL `task_schedules` table
- APScheduler service runs in gateway for execution
- Fully programmable via Discord commands and API
- Survives restarts and supports dynamic updates

### 4. Task Parameters ✅
**Decision**: Template-Based Parameters
- Tasks defined with parameter placeholders: `{destination}`, `{dates}`, `{price_threshold}`
- Required parameters must be provided when starting task
- Example: `/task-start ticket-checker destination:miami dates:next-week`
- Provides flexibility while maintaining structure

### 5. Result Formatting ✅
**Decision**: All Formats (Rich Experience)
- ✅ Rich embeds with summary and key metrics
- ✅ File attachments (CSV data, screenshots)
- ✅ Links to MinIO for full raw data
- ✅ Interactive buttons for quick actions (Run Again, Adjust, View Details)

### 6. Data Retention ✅
**Decision**: Keep Everything Forever
- Never auto-delete channels or database records
- Archive old threads but keep them accessible
- Full audit trail and history always available
- Manual cleanup commands available if needed

### 7. Multi-User Support ✅
**Decision**: Personal Tasks Only (Phase 1)
- Tasks tied to Discord user ID
- Each user creates and manages their own tasks
- No collaboration features initially
- Can expand to shared tasks in future phase

### 8. VNC Access ✅
**Decision**: Always-On VNC in Every Container
- VNC server (noVNC) runs in all browser task containers
- Instant access when human intervention needed
- Slightly higher resource usage but best debugging experience
- WebSocket proxy through gateway for secure access

### 9. Concurrency Limits ✅
**Decision**: 10 Concurrent Tasks Maximum
- System-wide limit: 10 simultaneous browser tasks
- Balanced for server resources and overlapping schedules
- Queue additional tasks if limit reached
- Configurable per deployment

### 10. Task Dependencies ✅
**Decision**: Support Dependency Chains
- Tasks can specify dependencies: "Run after task X completes"
- Enable multi-step workflows and pipelines
- Example: scrape-data → analyze-data → generate-report
- Acyclic dependency graphs enforced

### 11. Failure Handling ✅
**Decision**: Auto-Retry + User Notification
- Automatic retry with exponential backoff (3 attempts default)
- Notify user in Discord after each failure
- After max retries, wait for manual intervention
- Capture detailed failure reports (screenshots, logs, browser state)

### 12. Notifications ✅
**Decision**: Task Completion + Errors Only
- Notify on task completion (success)
- Notify on errors and failures
- No start notifications (reduces noise)
- No progress updates (unless task explicitly sends them)

### 13. Additional Notification Channels ✅
**Decision**: Pushover Integration
- Support Pushover for mobile push notifications
- Critical failures sent to Pushover in addition to Discord
- Configurable per user via settings
- Other channels (email, SMS) can be added later

### 14. Metrics Tracking ✅
**Decision**: Comprehensive Metrics
- ✅ Browser metrics: pages loaded, HTTP requests, data transferred
- ✅ Performance metrics: step durations, bottlenecks, load times
- ✅ Resource metrics: token usage, compute time (not cost calculation)
- Enable analysis and optimization over time

### 15. Slash Commands ✅
**Decision**: Full Command Set with Enhancements
- Core: `/task-create`, `/task-start`, `/task-stop`, `/task-list`, `/task-status`
- Scheduling: `/task-schedule`, `/task-schedule-remove`
- Management: `/task-pause`, `/task-resume`, `/task-delete`
- Templates: `/task-clone`, `/task-template-save`, `/task-template-load`
- Monitoring: `/task-history`, `/task-logs`, `/session-vnc`
- Dependencies: `/task-depends-on`, `/task-dependencies`

### 16. Template Library ✅
**Decision**: Shared Template Library
- Users can save tasks as reusable templates
- Pre-built templates for common use cases
- Templates stored in `task_templates` table
- Community sharing (within deployment)
- Version control for template updates

---

## Pushover Integration

### Overview

Pushover provides mobile push notifications for critical task events. This complements Discord notifications with instant mobile alerts.

### Configuration

**Environment Variables** (Gateway):
```bash
PUSHOVER_API_TOKEN=your_app_token_here  # CC-Docker app token
```

**User Settings** (per user):
```bash
# Users provide their own Pushover user keys via /settings command
/settings pushover-key <user_key>
/settings pushover-priority <-2|0|1|2>  # Default: 0 (normal)
```

### Push Notification Triggers

Pushover notifications sent for:
1. **Task Failure** (after all retry attempts exhausted)
2. **Human Intervention Required** (CAPTCHA, MFA, etc.)
3. **Task Complete** (if enabled by user, default: disabled)

### Pushover Priority Levels

| Priority | Description | Behavior |
|----------|-------------|----------|
| -2 | Silent | No sound/vibration, badge only |
| -1 | Quiet | No sound/vibration |
| 0 | Normal | Default notification |
| 1 | High | Bypasses quiet hours |
| 2 | Emergency | Requires acknowledgment, repeats until confirmed |

### Message Format

```
🚨 CC-Docker Alert

Task: ticket-checker
Status: Failed after 3 attempts
Error: Navigation timeout on kayak.com

View: https://discord.com/channels/.../thread/...
VNC: /session-vnc 3a7f2bc4
```

### API Integration

**Gateway Endpoint**:
```python
POST /api/v1/notifications/pushover
{
  "task_run_id": "uuid",
  "user_key": "user_key_from_db",
  "message": "Task ticket-checker failed",
  "priority": 1,
  "url": "https://discord.com/channels/...",
  "url_title": "View in Discord"
}
```

**Pushover API Call**:
```python
import requests

def send_pushover(user_key: str, message: str, priority: int = 0, url: str = None):
    """Send Pushover notification."""
    response = requests.post("https://api.pushover.net/1/messages.json", data={
        "token": PUSHOVER_API_TOKEN,
        "user": user_key,
        "message": message,
        "priority": priority,
        "url": url,
        "url_title": "View Details",
        "sound": "pushover"  # or "bike", "bugle", "cashregister", etc.
    })
    return response.json()
```

### User Commands

```
/settings pushover-key <key>
  Set your Pushover user key

/settings pushover-priority <level>
  Set default priority (-2 to 2)

/settings pushover-notify-on <events>
  Configure which events trigger Pushover
  Options: complete, error, intervention
  Default: error, intervention

/settings pushover-test
  Send test notification to verify setup

/settings pushover-disable
  Disable Pushover notifications
```

### Database Schema Addition

Covered in main schema under `pushover_notifications` table and task `pushover_enabled` fields.

---

## Finalized Database Schema

### Core Tables

```sql
-- Task Definitions
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_name VARCHAR(255) UNIQUE NOT NULL,
    task_type VARCHAR(50) NOT NULL,  -- ticket-checker, news-digest, price-monitor, etc.
    description TEXT,

    -- Template System
    template_prompt TEXT NOT NULL,  -- Prompt with {placeholders}
    required_parameters JSONB,      -- ["destination", "dates"] etc.
    optional_parameters JSONB,      -- ["price_threshold", "airline"] etc.

    -- Scheduling
    schedule_cron VARCHAR(100),  -- Cron expression
    schedule_timezone VARCHAR(50) DEFAULT 'UTC',
    enabled BOOLEAN DEFAULT TRUE,
    paused BOOLEAN DEFAULT FALSE,  -- Temporary pause without disabling
    next_run_at TIMESTAMP,
    last_run_at TIMESTAMP,

    -- Configuration
    config JSONB NOT NULL,  -- Full task config (mcp_servers, timeout, etc.)

    -- Discord
    discord_channel_id VARCHAR(64),
    discord_category_id VARCHAR(64),
    discord_thread_id_current VARCHAR(64),
    owner_user_id VARCHAR(64) NOT NULL,  -- Discord user ID

    -- Dependencies
    depends_on_tasks JSONB,  -- Array of task_ids that must complete first
    dependency_mode VARCHAR(20) DEFAULT 'all',  -- 'all' or 'any'

    -- Notifications
    pushover_enabled BOOLEAN DEFAULT FALSE,
    pushover_user_key VARCHAR(64),
    notify_on_complete BOOLEAN DEFAULT TRUE,
    notify_on_error BOOLEAN DEFAULT TRUE,

    -- Metadata
    run_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    avg_duration_seconds INTEGER,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(64) NOT NULL,
    deleted_at TIMESTAMP  -- Soft delete
);

CREATE INDEX idx_tasks_owner ON tasks(owner_user_id);
CREATE INDEX idx_tasks_next_run ON tasks(next_run_at) WHERE enabled = TRUE AND paused = FALSE;
CREATE INDEX idx_tasks_discord_channel ON tasks(discord_channel_id);
CREATE INDEX idx_tasks_dependencies ON tasks USING GIN(depends_on_tasks);

-- Task Runs
CREATE TABLE task_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id),
    session_id UUID REFERENCES sessions(id),

    -- Execution details
    status VARCHAR(20),  -- scheduled, waiting_dependency, starting, running, completed, failed, cancelled
    trigger VARCHAR(20), -- scheduled, manual, dependency, retry
    parameters JSONB,    -- Actual parameter values used for this run
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,

    -- Discord tracking
    discord_channel_id VARCHAR(64),
    discord_thread_id VARCHAR(64),
    discord_messages JSONB,  -- Array of message IDs posted

    -- Results
    result_summary TEXT,  -- Brief summary for display
    result_data JSONB,    -- Structured data (e.g., prices found)
    output_files JSONB,   -- Array of file URLs (screenshots, reports)
    minio_artifacts JSONB,  -- Links to MinIO stored data

    -- Error handling
    error_message TEXT,
    error_stacktrace TEXT,
    error_screenshot_url TEXT,
    retry_count INTEGER DEFAULT 0,
    retry_of UUID REFERENCES task_runs(id),  -- Parent run if this is a retry

    -- Human intervention
    required_intervention BOOLEAN DEFAULT FALSE,
    intervention_reason TEXT,  -- "captcha", "mfa", "unclear_result", "browser_crash"
    intervention_resolved_at TIMESTAMP,
    vnc_session_active BOOLEAN DEFAULT FALSE,
    vnc_accessed_at TIMESTAMP,

    -- Metrics
    tokens_used JSONB,           -- {input: X, output: Y}
    compute_time_seconds INTEGER,
    api_calls_made INTEGER,
    pages_loaded INTEGER,
    http_requests_made INTEGER,
    data_transferred_bytes BIGINT,
    step_timings JSONB,          -- Performance breakdown per step

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_task_runs_task_id ON task_runs(task_id);
CREATE INDEX idx_task_runs_status ON task_runs(status);
CREATE INDEX idx_task_runs_started_at ON task_runs(started_at DESC);
CREATE INDEX idx_task_runs_discord_thread ON task_runs(discord_thread_id);
CREATE INDEX idx_task_runs_intervention ON task_runs(required_intervention) WHERE required_intervention = TRUE;

-- Task Templates (Shared Library)
CREATE TABLE task_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_name VARCHAR(255) UNIQUE NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    description TEXT,

    template_prompt TEXT NOT NULL,
    required_parameters JSONB,
    optional_parameters JSONB,
    default_config JSONB,

    author_user_id VARCHAR(64) NOT NULL,
    is_public BOOLEAN DEFAULT FALSE,
    use_count INTEGER DEFAULT 0,
    rating_average DECIMAL(3,2),

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    version INTEGER DEFAULT 1
);

CREATE INDEX idx_task_templates_type ON task_templates(template_type);
CREATE INDEX idx_task_templates_public ON task_templates(is_public) WHERE is_public = TRUE;
CREATE INDEX idx_task_templates_author ON task_templates(author_user_id);

-- Discord Channels Registry
CREATE TABLE discord_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id VARCHAR(64) UNIQUE NOT NULL,
    channel_name VARCHAR(100) NOT NULL,
    category_id VARCHAR(64),
    category_name VARCHAR(100),
    channel_type VARCHAR(20), -- task, task-category, admin

    task_id UUID REFERENCES tasks(id),

    created_at TIMESTAMP DEFAULT NOW(),
    archived_at TIMESTAMP,

    metadata JSONB  -- Additional channel info
);

CREATE INDEX idx_discord_channels_task ON discord_channels(task_id);
CREATE INDEX idx_discord_channels_category ON discord_channels(category_id);

-- Discord Threads Registry
CREATE TABLE discord_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id VARCHAR(64) UNIQUE NOT NULL,
    thread_name VARCHAR(100) NOT NULL,
    parent_channel_id VARCHAR(64) NOT NULL,

    task_run_id UUID REFERENCES task_runs(id),
    session_id UUID REFERENCES sessions(id),

    status VARCHAR(20), -- running, complete, failed

    created_at TIMESTAMP DEFAULT NOW(),
    archived_at TIMESTAMP,

    metadata JSONB
);

CREATE INDEX idx_discord_threads_task_run ON discord_threads(task_run_id);
CREATE INDEX idx_discord_threads_status ON discord_threads(status);

-- Discord Messages Log
CREATE TABLE discord_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id VARCHAR(64) UNIQUE NOT NULL,
    channel_id VARCHAR(64) NOT NULL,
    thread_id VARCHAR(64),

    task_run_id UUID REFERENCES task_runs(id),
    interaction_id UUID REFERENCES discord_interactions(id),

    message_type VARCHAR(50), -- task_start, task_progress, task_complete, task_error, ask_user, notification, result
    content TEXT,
    embeds JSONB,
    attachments JSONB,
    buttons JSONB,  -- Interactive button components

    sent_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_discord_messages_task_run ON discord_messages(task_run_id);
CREATE INDEX idx_discord_messages_channel ON discord_messages(channel_id);
CREATE INDEX idx_discord_messages_type ON discord_messages(message_type);

-- Schedule History
CREATE TABLE schedule_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id),

    action VARCHAR(50), -- created, updated, removed, triggered, paused, resumed
    schedule_before VARCHAR(100),
    schedule_after VARCHAR(100),

    triggered_by VARCHAR(20), -- scheduler, user_command, api, dependency
    user_id VARCHAR(64),  -- Discord user ID if manual

    timestamp TIMESTAMP DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX idx_schedule_history_task ON schedule_history(task_id);
CREATE INDEX idx_schedule_history_action ON schedule_history(action);

-- Task Dependencies (explicit relationship table)
CREATE TABLE task_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id),  -- Dependent task
    depends_on_task_id UUID REFERENCES tasks(id),  -- Task that must complete first

    required BOOLEAN DEFAULT TRUE,  -- Must succeed or just complete?
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(64),

    UNIQUE(task_id, depends_on_task_id)
);

CREATE INDEX idx_task_dependencies_task ON task_dependencies(task_id);
CREATE INDEX idx_task_dependencies_depends ON task_dependencies(depends_on_task_id);

-- Pushover Notifications Log
CREATE TABLE pushover_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_run_id UUID REFERENCES task_runs(id),

    user_key VARCHAR(64) NOT NULL,
    message TEXT NOT NULL,
    priority INTEGER DEFAULT 0,  -- -2 to 2 (Pushover priority levels)

    sent_at TIMESTAMP DEFAULT NOW(),
    pushover_response JSONB,
    success BOOLEAN
);

CREATE INDEX idx_pushover_notifications_task_run ON pushover_notifications(task_run_id);
CREATE INDEX idx_pushover_notifications_sent_at ON pushover_notifications(sent_at DESC);
```

---

## Discord Slash Commands (Complete List)

### Task Creation & Management

```
/task-create <name> <prompt_template>
  Description: Define a new task with parameter placeholders
  Example: /task-create ticket-checker "Check flights from {origin} to {destination} on {dates}"
  Parameters:
    - name: Unique task identifier
    - prompt_template: Prompt with {parameter} placeholders
  Creates: Discord channel, database record

/task-delete <task_name>
  Description: Delete task definition and all history
  Confirmation: Required (shows run count, asks for confirmation)
  Effect: Soft delete (sets deleted_at timestamp)

/task-clone <source_task> <new_name>
  Description: Duplicate an existing task with new name
  Copies: Template, config, parameters, schedule
  Creates: New Discord channel

/task-edit <task_name> [field] [value]
  Description: Modify task configuration
  Fields: description, prompt, timeout, notify_on_complete, notify_on_error
  Example: /task-edit ticket-checker timeout 3600
```

### Task Execution

```
/task-start <task_name> [param1:value1] [param2:value2]
  Description: Start task immediately with parameters
  Example: /task-start ticket-checker origin:SFO destination:HNL dates:next-week
  Validation: Checks required parameters provided
  Returns: Session ID, thread link

/task-stop <task_name_or_session_id>
  Description: Stop currently running task
  Effect: Graceful shutdown, marks as cancelled
  Options: --force for immediate termination

/task-continue <session_id>
  Description: Signal that manual intervention is complete
  Use case: After solving captcha via VNC
  Effect: Resumes task execution
```

### Scheduling

```
/task-schedule <task_name> <cron_expression> [timezone]
  Description: Set or update task schedule
  Example: /task-schedule news-digest "0 9 * * *" America/Los_Angeles
  Validation: Validates cron expression
  Returns: Next 5 scheduled run times

/task-schedule-remove <task_name>
  Description: Remove schedule (keeps task definition)
  Effect: Sets schedule_cron to NULL

/task-pause <task_name>
  Description: Temporarily pause scheduled task
  Effect: Sets paused=TRUE, skips scheduled runs
  Note: Different from stop (stops current run) vs disable (removes schedule)

/task-resume <task_name>
  Description: Resume paused task
  Effect: Sets paused=FALSE, resumes scheduled runs
```

### Monitoring & Status

```
/task-status [task_name]
  Description: Show task status and current runs
  Without task_name: Shows all user's tasks
  With task_name: Shows detailed status, current runs, next run time
  Display: Rich embed with metrics

/task-list [filter]
  Description: List all defined tasks
  Filters: active, paused, failed, scheduled
  Display: Table with name, schedule, last run, success rate

/task-history <task_name> [limit]
  Description: Show recent runs of a task
  Default limit: 10
  Display: Table with timestamp, duration, status, result summary

/task-logs <session_id>
  Description: Get detailed logs for specific run
  Returns: Attached log file or paginated output
  Includes: Claude output, browser logs, error traces

/task-metrics <task_name> [timeframe]
  Description: Show task metrics and analytics
  Timeframes: day, week, month, all
  Display: Success rate, avg duration, tokens used, cost estimation
```

### Templates

```
/task-template-save <task_name> <template_name> [public]
  Description: Save task as reusable template
  Options: public=true to share with all users
  Creates: Entry in task_templates table

/task-template-load <template_name> <new_task_name>
  Description: Create task from template
  Copies: Prompt template, parameters, default config
  Creates: New task and Discord channel

/task-template-list [filter]
  Description: List available templates
  Filters: mine, public, type:<task_type>
  Display: Template name, author, use count, rating

/task-template-delete <template_name>
  Description: Delete template (author only)
  Confirmation: Required if use_count > 0
```

### Dependencies

```
/task-depends-on <task_name> <depends_on_task> [required]
  Description: Add task dependency
  Example: /task-depends-on analyze-data scrape-data required:true
  Effect: analyze-data only runs after scrape-data completes
  Option: required=true means dependency must succeed (not just complete)

/task-dependencies <task_name>
  Description: Show task dependencies
  Display: Tree view of dependencies (parents and children)

/task-depends-remove <task_name> <depends_on_task>
  Description: Remove dependency relationship
```

### VNC & Intervention

```
/session-vnc <session_id>
  Description: Get VNC access credentials
  Returns:
    - VNC URL (WebSocket proxy through gateway)
    - Temporary password (expires in 30 minutes)
    - Connection instructions
  Opens: VNC viewer in browser tab

/task-vnc-list
  Description: List sessions with active VNC access
  Shows: Session ID, task name, intervention reason, time active

/task-intervention-resolve <session_id>
  Description: Mark intervention as resolved
  Same as: /task-continue
  Use: Alternative command name for clarity
```

### Advanced

```
/task-retry <session_id>
  Description: Retry a failed task run
  Effect: Creates new run as retry of failed run
  Parameters: Can override with new parameter values

/task-config <task_name> [show|edit]
  Description: View or edit full task configuration (JSON)
  show: Returns JSON config
  edit: Opens modal for JSON editing
  Advanced: For power users

/task-export <task_name>
  Description: Export task definition as JSON
  Use case: Backup, sharing, version control
  Returns: JSON file download

/task-import <json_file>
  Description: Import task definition from JSON
  Creates: New task with all configuration
  Validation: Checks for conflicts (name, dependencies)
```

---

## Implementation Plan

### Phase 1: Foundation & Database (Week 1)

**Goals**: Core infrastructure and data models

**Tasks**:
1. Implement complete database schema (tasks, task_runs, templates, dependencies)
2. Create database migrations and seed data
3. Task CRUD API endpoints (create, read, update, delete)
4. Task parameter validation and template engine
5. Unit tests for data models

**Deliverables**:
- PostgreSQL schema fully deployed
- REST API endpoints for task management
- Parameter template system working

### Phase 2: Discord Bot & Slash Commands (Week 2)

**Goals**: Discord integration and basic commands

**Tasks**:
1. Discord bot enhancements for slash command registration
2. Implement core commands: `/task-create`, `/task-start`, `/task-stop`, `/task-list`
3. Auto-create Discord channels on task creation
4. Discord thread creation for task runs
5. Rich embed formatting for task status

**Deliverables**:
- All core slash commands working
- Channel/thread auto-creation
- Task status embeds

### Phase 3: Task Scheduling & Execution (Week 3)

**Goals**: APScheduler integration and automated execution

**Tasks**:
1. APScheduler service in gateway
2. Schedule management: `/task-schedule`, `/task-pause`, `/task-resume`
3. Dependency resolution engine (DAG validation)
4. Scheduled task trigger with parameter filling
5. Concurrency limits (10 max simultaneous tasks)
6. Task queue for overflow

**Deliverables**:
- Cron-based scheduling working
- Dependency chains functional
- Concurrency management

### Phase 4: Results & Notifications (Week 4)

**Goals**: Rich result formatting and multi-channel notifications

**Tasks**:
1. Result formatting: embeds, attachments, buttons
2. Screenshot capture and MinIO upload
3. CSV/structured data export
4. Discord notification on completion/error
5. Pushover integration for mobile alerts
6. Interactive buttons (Run Again, View Details, etc.)

**Deliverables**:
- Rich result displays in Discord
- Pushover notifications working
- Interactive message buttons

### Phase 5: VNC & Human Intervention (Week 5)

**Goals**: Manual intervention support

**Tasks**:
1. noVNC in container image (always-on)
2. VNC WebSocket proxy in gateway
3. `/session-vnc` command with temporary auth tokens
4. Automatic captcha/MFA detection (via Claude Code)
5. Intervention resolution tracking
6. VNC access logging and security

**Deliverables**:
- VNC accessible from Discord
- Secure token-based access
- Intervention tracking

### Phase 6: Template Library & Dependencies (Week 6)

**Goals**: Reusable templates and advanced orchestration

**Tasks**:
1. Template save/load functionality
2. Template marketplace (public templates)
3. Template rating system
4. Dependency visualization in Discord
5. `/task-depends-on` and dependency commands
6. Pre-built templates for common tasks

**Deliverables**:
- Template library functional
- Public template sharing
- Dependency management

### Phase 7: Monitoring & Analytics (Week 7)

**Goals**: Comprehensive monitoring and metrics

**Tasks**:
1. `/task-history`, `/task-logs`, `/task-metrics` commands
2. Browser metrics collection (pages loaded, requests)
3. Performance metrics (step timings, bottlenecks)
4. Token usage and compute time tracking
5. Dashboard embeds with charts
6. Export metrics to CSV

**Deliverables**:
- Full task history accessible
- Performance analytics
- Metrics visualization

### Phase 8: Error Handling & Retries (Week 8)

**Goals**: Robust failure handling

**Tasks**:
1. Automatic retry with exponential backoff
2. Failure notifications to Discord
3. Detailed failure reports (screenshots, logs, state)
4. `/task-retry` command
5. Max retry limits and backoff configuration
6. Failure pattern detection

**Deliverables**:
- Auto-retry working
- Failure reports comprehensive
- Manual retry command

### Phase 9: Advanced Commands & Polish (Week 9)

**Goals**: Advanced features and UX improvements

**Tasks**:
1. `/task-clone`, `/task-edit`, `/task-config` commands
2. `/task-export`, `/task-import` for backup
3. Task parameter autocomplete in Discord
4. Channel organization by category
5. Thread archival (keep forever strategy)
6. Rate limiting for task starts

**Deliverables**:
- All advanced commands working
- Polished UX
- Import/export functional

### Phase 10: Testing & Documentation (Week 10)

**Goals**: Production readiness

**Tasks**:
1. End-to-end integration tests
2. Load testing (10 concurrent tasks)
3. Security audit (VNC access, permissions)
4. User documentation
5. Admin guide for deployment
6. Performance optimization

**Deliverables**:
- Comprehensive test suite
- Production-ready deployment
- Complete documentation

---

## Complete Example Workflows

### Workflow 1: Creating a Parameterized Task with Schedule

```
User: /task-create ticket-checker "Check flight prices from {origin} to {destination} for travel on {dates}. Find cheapest options and report top 5. Alert if price drops below ${price_threshold}."

Bot: ✅ Task created: ticket-checker

     📝 Required parameters: origin, destination, dates
     📝 Optional parameters: price_threshold (default: 500)

     📁 Category: Ticket Price Monitoring
     📢 Channel created: #ticket-checker

     Use /task-schedule to set up automatic runs

User: /task-schedule ticket-checker "0 6,18 * * *" America/Los_Angeles

Bot: ✅ Schedule configured for ticket-checker
     ⏰ Runs every day at 6:00 AM and 6:00 PM PST

     📅 Next 5 runs:
       • 2026-01-18 06:00 PST
       • 2026-01-18 18:00 PST
       • 2026-01-19 06:00 PST
       • 2026-01-19 18:00 PST
       • 2026-01-20 06:00 PST

     ⚠️  Note: Scheduled runs require default parameter values.
         Use /task-edit to set defaults or parameters will be prompted.
```

### Workflow 2: Manual Task Execution with Parameters

```
User: /task-start ticket-checker origin:SFO destination:HNL dates:"Feb 15-22" price_threshold:400

Bot: 🚀 Starting task: ticket-checker

     Session ID: 3a7f2bc4-1d9e-4a23-8f61-5c9d4e3b2a10
     Parameters:
       • origin: SFO
       • destination: HNL
       • dates: Feb 15-22
       • price_threshold: $400

     📊 View progress in thread ↓

(Bot creates thread: "Run 2026-01-17 15:30 - Running")

Bot (in thread): 🌐 Starting browser automation...
Bot (in thread): 🔍 Navigating to kayak.com...
Bot (in thread): ✈️  Searching flights SFO → HNL (Feb 15-22)...
Bot (in thread): 📊 Analyzing 47 flight options...
Bot (in thread): ✅ Task complete!

(Bot posts rich embed)

╔═══════════════════════════════════════════════╗
║ ✅ Task Complete: Ticket Price Checker        ║
╠═══════════════════════════════════════════════╣
║ Duration: 2m 38s                              ║
║ Completed: 2026-01-17 15:32:38 PST           ║
╠═══════════════════════════════════════════════╣
║ 🎫 Cheapest Flights Found (SFO → HNL):       ║
║                                               ║
║ 1. United Airlines: $342 (Feb 15-22)         ║
║    • Departs: 9:15 AM, 1 stop (LAX)         ║
║    • Returns: 3:45 PM, Nonstop              ║
║                                               ║
║ 2. Southwest: $378 (Feb 15-22)               ║
║    • Departs: 11:30 AM, Nonstop             ║
║    • Returns: 5:00 PM, Nonstop              ║
║                                               ║
║ 3. Hawaiian Airlines: $395 (Feb 16-23)       ║
║    • Departs: 7:00 AM, Nonstop              ║
║    • Returns: 2:30 PM, Nonstop              ║
║                                               ║
║ 4. Alaska Airlines: $412 (Feb 15-22)         ║
║ 5. Delta: $445 (Feb 15-22)                   ║
║                                               ║
║ 🔔 Price Alert: 2 options below $400!        ║
╚═══════════════════════════════════════════════╝

[Run Again] [Adjust Dates] [View Full Report] [Save Template]

Attachments:
  📎 flight_results.csv (5.2 KB)
  📎 kayak_screenshot.png (342 KB)
  🔗 Full data: https://minio.example.com/tasks/3a7f2bc4/results.json

Metrics:
  • Pages loaded: 12
  • HTTP requests: 247
  • Data transferred: 8.3 MB
  • Tokens used: 2,847 (input: 1,203 | output: 1,644)
  • Compute time: 158 seconds
```

### Workflow 3: Human Intervention (CAPTCHA)

```
(Task running in thread)

Bot (in thread): 🌐 Navigating to kayak.com...
Bot (in thread): 🚨 Manual intervention required

╔═══════════════════════════════════════════════╗
║ ⚠️  Human Intervention Needed                 ║
╠═══════════════════════════════════════════════╣
║ Task: ticket-checker                          ║
║ Issue: CAPTCHA detected (reCAPTCHA v2)       ║
║ Location: kayak.com/flights                   ║
║ Status: Waiting for resolution...            ║
╚═══════════════════════════════════════════════╝

[Open VNC Session] 🖥️

User: (clicks "Open VNC Session" button)

Bot (DM): 🖥️ VNC Access Credentials

     URL: https://gateway.example.com/vnc/3a7f2bc4?token=xyz789abc
     Password: temp_Pass_8x3K

     ⏰ Access expires in: 30 minutes
     📱 Session ID: 3a7f2bc4-1d9e-4a23-8f61-5c9d4e3b2a10

     Instructions:
     1. Click URL to open VNC viewer in new tab
     2. Enter password when prompted
     3. Solve the CAPTCHA in the browser
     4. Task will resume automatically

     Use /task-continue 3a7f2bc4 if task doesn't resume after 1 minute.

(User opens VNC, solves CAPTCHA)

Bot (in thread): ✅ CAPTCHA resolved! Continuing...
Bot (in thread): 🔍 Searching flights SFO → HNL...
Bot (in thread): ✅ Task complete!

(Bot posts results as above)
```

### Workflow 4: Task Dependencies (Multi-Step Workflow)

```
User: /task-create scrape-tech-news "Visit TechCrunch, Ars Technica, Hacker News. Extract top 10 articles from each. Save to {output_file}."

Bot: ✅ Task created: scrape-tech-news
     Required parameters: output_file
     Channel: #scrape-tech-news

User: /task-create analyze-tech-news "Read {input_file}, categorize articles by topic (AI, Security, Web3, etc.), identify trending themes. Generate summary report."

Bot: ✅ Task created: analyze-tech-news
     Required parameters: input_file
     Channel: #analyze-tech-news

User: /task-create generate-digest "Read {analysis_file}, write engaging newsletter in Markdown. Include top 5 stories with summaries. Output to {output_file}."

Bot: ✅ Task created: generate-digest
     Required parameters: analysis_file, output_file
     Channel: #generate-digest

User: /task-depends-on analyze-tech-news scrape-tech-news required:true

Bot: ✅ Dependency added
     Task 'analyze-tech-news' will run after 'scrape-tech-news' completes successfully

User: /task-depends-on generate-digest analyze-tech-news required:true

Bot: ✅ Dependency added
     Task 'generate-digest' will run after 'analyze-tech-news' completes successfully

User: /task-dependencies generate-digest

Bot: 📊 Task Dependency Tree: generate-digest

     generate-digest
       ↑ depends on
     analyze-tech-news
       ↑ depends on
     scrape-tech-news

     🔗 Total depth: 2 levels
     ⏱️  Estimated total time: ~15 minutes

User: /task-schedule scrape-tech-news "0 7 * * *"

Bot: ✅ Scheduled: scrape-tech-news (7:00 AM daily)

     🔗 This will trigger dependent tasks:
       1. analyze-tech-news (starts after scrape completes)
       2. generate-digest (starts after analyze completes)

     Complete workflow will run daily at 7:00 AM

(Next day at 7:00 AM)

Bot (in #scrape-tech-news): 🚀 Starting scheduled task: scrape-tech-news
Bot: (creates thread, executes task)
Bot: ✅ Complete! 30 articles scraped → tech_news_2026-01-18.json

Bot (in #analyze-tech-news): 🔗 Starting dependent task: analyze-tech-news
Bot: (creates thread, executes task)
Bot: ✅ Complete! Analysis generated → tech_analysis_2026-01-18.json

Bot (in #generate-digest): 🔗 Starting dependent task: generate-digest
Bot: (creates thread, executes task)
Bot: ✅ Complete! Newsletter generated → tech_digest_2026-01-18.md

Bot (main notification channel): 📬 Daily Tech News Digest Ready!

     All 3 tasks completed successfully:
       ✅ scrape-tech-news (2m 15s)
       ✅ analyze-tech-news (1m 42s)
       ✅ generate-digest (0m 58s)

     📎 tech_digest_2026-01-18.md (12 KB)

     [View Digest] [Email to Self] [Post to Blog]
```

### Workflow 5: Template Usage

```
User: /task-template-list type:ticket-checker

Bot: 📚 Available Templates (ticket-checker)

     1. flights-domestic-usa
        Author: @system | Uses: 127 | Rating: ⭐⭐⭐⭐⭐
        Checks major airlines for domestic US flights

     2. concerts-ticketmaster
        Author: @system | Uses: 89 | Rating: ⭐⭐⭐⭐
        Monitors Ticketmaster for concert ticket availability

     3. hotel-price-monitor
        Author: @john_doe | Uses: 34 | Rating: ⭐⭐⭐⭐
        Tracks hotel prices across Booking.com, Hotels.com

     Use /task-template-load <template_name> <new_task_name> to create task

User: /task-template-load flights-domestic-usa my-miami-flight-checker

Bot: ✅ Task created from template: my-miami-flight-checker

     📝 Template: flights-domestic-usa
     📁 Channel: #my-miami-flight-checker

     Required parameters (from template):
       • origin: Airport code (e.g., SFO)
       • destination: Airport code (e.g., MIA)
       • departure_date: Format YYYY-MM-DD
       • return_date: Format YYYY-MM-DD

     Optional parameters:
       • max_price: Default $500
       • preferred_airlines: Default "any"
       • max_stops: Default 1

     Template includes:
       ✅ Browser automation for United, Delta, Southwest, American
       ✅ Price comparison logic
       ✅ Alert thresholds
       ✅ Screenshot capture

     Ready to use! Set schedule or run manually.

User: /task-start my-miami-flight-checker origin:SFO destination:MIA departure_date:2026-03-15 return_date:2026-03-22 max_price:450

Bot: 🚀 Starting task...
     (executes with template's proven workflow)
```

---

## Summary

This specification defines a comprehensive Discord-driven task automation system for CC-Docker that enables scheduled browser-based tasks with human-in-the-loop oversight.

### Key Features Approved

✅ **Hybrid Channel Model**: Persistent task channels + threads per run
✅ **Template-Based Parameters**: Flexible task definitions with `{placeholders}`
✅ **APScheduler**: Database-driven cron scheduling
✅ **Task Dependencies**: Multi-step workflows (A → B → C)
✅ **Always-On VNC**: Instant access for captcha/MFA intervention
✅ **Rich Results**: Embeds + attachments + MinIO links + interactive buttons
✅ **Pushover Integration**: Mobile push notifications for critical events
✅ **Comprehensive Metrics**: Browser stats, performance, token usage
✅ **Template Library**: Shared, reusable task templates
✅ **Auto-Retry**: Exponential backoff with user notification
✅ **10 Concurrent Tasks**: Balanced resource limits
✅ **Keep Forever**: No auto-deletion of channels or data
✅ **45+ Slash Commands**: Complete Discord control surface

### Architecture Highlights

- **PostgreSQL**: 10+ tables for tasks, runs, templates, dependencies, notifications
- **Discord Bot**: Slash command registration + channel management + thread lifecycle
- **APScheduler**: Cron-based scheduling with dependency resolution
- **noVNC**: Browser-accessible VNC for manual intervention
- **Pushover**: Mobile alerts for failures and interventions
- **MinIO**: Artifact storage (screenshots, CSVs, reports)

### Use Cases Enabled

1. **Ticket Price Monitoring**: Check flight/concert/hotel prices on schedule
2. **News Digests**: Scrape → analyze → generate daily newsletters
3. **Competitor Monitoring**: Track pricing, features, availability
4. **Web Scraping**: Extract data from websites with captcha handling
5. **Multi-Step Workflows**: Orchestrate complex task chains
6. **Template Sharing**: Reuse proven task configurations

### Next Steps for Implementation

1. ✅ Architecture decisions finalized
2. ✅ Database schema approved
3. ✅ Slash commands defined
4. ✅ User flows documented
5. → Begin Phase 1: Database implementation
6. → Set up development environment
7. → Create GitHub issues for each phase
8. → Start building!

---

## Appendix: Decision Record

All architecture decisions in this spec were approved by the user on 2026-01-17 via interactive questioning. This document serves as the source of truth for implementation.

**Approver**: User (grant.harris)
**Date**: 2026-01-17
**Method**: AskUserQuestion tool (4 rounds)
**Status**: Ready for Implementation
