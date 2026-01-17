# Discord Bot Setup Guide

This guide walks you through creating and configuring a Discord bot for CC-Docker to enable Claude Code instances to communicate with you via Discord.

## Overview

The Discord integration allows CC instances to:
- **Ask questions** and wait for your response before continuing
- **Send notifications** when tasks are complete or important events occur
- **Request intervention** for captchas, interactive terminals, or browser issues

All communication happens in a Discord channel (default: `#general`), with each question posted as a thread for organization.

## Prerequisites

- A Discord account
- Administrator access to a Discord server (or ability to create one)

## Step 1: Create a Discord Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"** in the top-right
3. Enter a name: `CC-Docker Bot` (or your preferred name)
4. Click **"Create"**

## Step 2: Create a Bot User

1. In your application, navigate to the **"Bot"** tab in the left sidebar
2. Click **"Add Bot"**
3. Confirm by clicking **"Yes, do it!"**
4. Under the bot's username, click **"Reset Token"** and then **"Copy"**
   - ⚠️ **Save this token securely** - you'll need it for configuration
   - This is your `DISCORD_BOT_TOKEN`

### Recommended Bot Settings

While on the Bot page, configure these settings:

- **Public Bot**: OFF (unless you want others to add your bot)
- **Requires OAuth2 Code Grant**: OFF
- **Presence Intent**: ON
- **Server Members Intent**: ON
- **Message Content Intent**: ON ⚠️ (Required for reading replies)

## Step 3: Configure Bot Permissions

1. Navigate to the **"OAuth2" → "URL Generator"** tab
2. Under **"Scopes"**, select:
   - ✅ `bot`
3. Under **"Bot Permissions"**, select:
   - ✅ `Send Messages`
   - ✅ `Send Messages in Threads`
   - ✅ `Create Public Threads`
   - ✅ `Read Message History`
   - ✅ `View Channels`
   - ✅ `Use Slash Commands` (optional, for future features)

The generated URL at the bottom will look like:
```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=326417525760&scope=bot
```

## Step 4: Invite Bot to Your Server

1. Copy the URL generated in Step 3
2. Paste it into your browser
3. Select the Discord server you want to add the bot to
4. Click **"Authorize"**
5. Complete the captcha if prompted

Your bot should now appear in your server's member list (offline until you start CC-Docker).

## Step 5: Get Your Channel ID

The bot needs to know which channel to post to.

### Enable Developer Mode (if not already enabled)
1. In Discord, go to **User Settings** (⚚ icon)
2. Navigate to **Advanced**
3. Enable **Developer Mode**

### Get the Channel ID
1. Right-click on the channel you want to use (e.g., `#general`)
2. Click **"Copy Channel ID"**
3. Save this - you'll need it for configuration
   - This is your `DISCORD_CHANNEL_ID`

## Step 6: Configure CC-Docker

Add the following to your `.env` file:

```bash
# Discord Integration
DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
DISCORD_CHANNEL_ID=YOUR_CHANNEL_ID_HERE

# Optional: Customize behavior
DISCORD_QUESTION_TIMEOUT=1800        # 30 minutes per attempt
DISCORD_MAX_RETRIES=3                # Total attempts before failing
DISCORD_UPDATE_INTERVAL=300          # Update countdown every 5 minutes
```

### Example `.env` file

```bash
# JWT Secret
JWT_SECRET=your-secret-key

# PostgreSQL Database
POSTGRES_USER=ccadmin
POSTGRES_PASSWORD=change-me-in-production
POSTGRES_DB=ccdocker

# MinIO
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Discord Integration
DISCORD_BOT_TOKEN=your-bot-token-from-discord-developer-portal
DISCORD_CHANNEL_ID=987654321098765432

# MCP Secrets (if using)
CC_SECRET_GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

## Step 7: Restart CC-Docker

```bash
docker-compose down
docker-compose up -d
```

Check the gateway logs to confirm the bot connected:

```bash
docker-compose logs -f gateway
```

You should see:
```
INFO - Discord bot connected as CC-Docker Bot#1234
INFO - Monitoring channel: #general (987654321098765432)
```

The bot should now show as **online** in your Discord server.

## Step 8: Test the Integration

### Test Notification (optional manual test)

You can test by making a request to the gateway API:

```bash
# Get a test token
TOKEN=$(curl -s http://localhost:8000/api/v1/test-token | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Send a test notification
curl -X POST http://localhost:8000/api/v1/discord/notify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-123",
    "message": "Test notification from CC-Docker!",
    "priority": "normal"
  }'
```

You should see a message appear in your Discord channel.

### Test Question (full integration test)

Create a session and send a prompt that triggers a question:

```bash
# This will be tested automatically once the full integration is complete
```

## Troubleshooting

### Bot is offline in Discord

**Check gateway logs:**
```bash
docker-compose logs -f gateway | grep -i discord
```

**Common issues:**
- Invalid token: Double-check `DISCORD_BOT_TOKEN` in `.env`
- Network issues: Ensure gateway container has internet access
- Token was reset: Generate a new token in Discord Developer Portal

### Bot doesn't respond to messages

**Check permissions:**
- Ensure "Message Content Intent" is enabled in Discord Developer Portal
- Verify bot has "Read Message History" permission in your server
- Check that bot has access to the channel (not a private channel unless bot is added)

**Check logs:**
```bash
docker-compose logs -f gateway | grep -i "discord.*message"
```

### Messages appear but countdown doesn't update

- This is normal if `DISCORD_UPDATE_INTERVAL` is set high
- Check gateway logs for any errors during updates
- Verify bot has "Send Messages in Threads" permission

### Questions timeout immediately

- Check `DISCORD_QUESTION_TIMEOUT` is set correctly (in seconds)
- Verify Redis is running: `docker-compose ps redis`
- Check gateway logs for timeout-related errors

## Discord Message Examples

### Question Message
```
🤔 **Question from Session abc-123**

Should I proceed with the database migration?

⏱️ Timeout: 30 minutes remaining (Attempt 1/3)
📝 Reply in this thread to answer

Session: abc-123 | Created: 2025-01-17 14:30:00
```

### Notification Message
```
✅ **Session abc-123 Complete**

Task: Refactored authentication module

Summary:
- Updated auth.py with OAuth 2.0
- Created 15 new tests
- All tests passing

Session: abc-123 | Completed: 2025-01-17 15:45:00
```

### Retry Message
```
⏰ **Still waiting for response...**

Original question: Should I proceed with the database migration?

⏱️ Timeout: 30 minutes remaining (Attempt 2/3)
📝 Reply in this thread to answer
```

## Security Considerations

- **Keep your bot token secret**: Never commit it to git or share publicly
- **Use environment variables**: Always configure via `.env` file
- **Private server recommended**: Consider using a private Discord server
- **Message history**: All questions and responses are logged in SQLite for audit

## Advanced Configuration

### Custom Emoji/Formatting

Edit `gateway/app/services/discord.py` to customize:
- Emoji used for different message types
- Message formatting and colors
- Embed styling

### Per-Session Channels (future)

This feature is planned but not yet implemented. It will allow each session to have its own dedicated Discord channel for cleaner organization.

## Related Documentation

- [SPEC-PLUGINS.md](../SPEC-PLUGINS.md) - MCP server details
- [CLAUDE.md](../CLAUDE.md) - Development guide
- [Discord.py Documentation](https://discordpy.readthedocs.io/)
