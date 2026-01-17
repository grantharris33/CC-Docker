#!/bin/bash
# Test script for CC-Docker Discord integration

set -e

echo "=== CC-Docker Discord Integration Test ==="
echo

# Get a test token
echo "1. Getting authentication token..."
TOKEN=$(curl -s http://localhost:8000/api/v1/test-token | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo "✓ Token obtained"
echo

# Create a session
echo "2. Creating test session..."
SESSION_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace": {"type": "ephemeral"},
    "config": {
      "mcp_servers": {"cc-docker": {"enabled": true}},
      "secrets": []
    }
  }')

SESSION_ID=$(echo $SESSION_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "✓ Session created: $SESSION_ID"
echo

# Test notification
echo "3. Testing Discord notification..."
NOTIFY_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/discord/notify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"message\": \"🎉 Test notification from CC-Docker at $(date)\",
    \"priority\": \"normal\"
  }")

INTERACTION_ID=$(echo $NOTIFY_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['interaction_id'])")
echo "✓ Notification sent with interaction ID: $INTERACTION_ID"
echo "  Check your Discord channel #general for the message!"
echo

# Test ask_user (with short timeout for demo)
echo "4. Testing Discord question (will wait up to 60 seconds for response)..."
echo "  Go to Discord and reply in the thread that will be created!"
echo

ASK_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/discord/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"question\": \"What's your favorite color? (This is a test question)\",
    \"context\": \"Testing the Discord ask_user integration\",
    \"timeout_seconds\": 60
  }" || echo '{"error": "Timeout waiting for response"}')

echo
echo "Response received:"
echo "$ASK_RESPONSE" | python3 -c "import sys,json; data=json.load(sys.stdin); print(f\"  Answer: {data.get('response', 'No response (timeout)')}\"); print(f\"  Interaction ID: {data.get('interaction_id', 'N/A')}\")" 2>/dev/null || echo "  Timeout or error occurred"
echo

# View interactions in database
echo "5. Database records:"
docker exec cc-docker-postgres-1 psql -U ccadmin -d ccdocker -t -c \
  "SELECT interaction_type || ': ' || status || ' - ' || substring(message, 1, 50) || '...'
   FROM discord_interactions
   WHERE session_id = '$SESSION_ID'
   ORDER BY created_at;" | sed 's/^/ /'

echo
echo "=== Test Complete ==="
echo
echo "Summary:"
echo "- Session ID: $SESSION_ID"
echo "- Check your Discord channel for the notification and question thread"
echo "- View all interactions: docker exec cc-docker-postgres-1 psql -U ccadmin -d ccdocker -c \"SELECT * FROM discord_interactions WHERE session_id = '$SESSION_ID';\""
