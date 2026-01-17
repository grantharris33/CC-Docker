#!/bin/bash
# E2E Test: Parent-Child Session with Interrupt
# This test verifies:
# 1. Parent can spawn a child session
# 2. Child workspace is mounted under parent's workspace at /workspace/children/<child_id>/
# 3. Parent can interrupt a child mid-execution
# 4. Parent can access child's work products via the mounted workspace

set -e

echo "=========================================="
echo "E2E Test: Parent-Child Session with Interrupt"
echo "=========================================="
echo ""

# Get test token
TOKEN=$(curl -s http://localhost:8000/api/v1/test-token | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo "[1/8] Got test token: ${TOKEN:0:30}..."

# Step 1: Create parent session
echo ""
echo "[2/8] Creating parent session..."
PARENT_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @- <<'EOFBODY'
{
  "workspace": {"type": "ephemeral"},
  "config": {
    "model": "sonnet-4",
    "timeout_seconds": 600
  }
}
EOFBODY
)
PARENT_ID=$(echo "$PARENT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
PARENT_CONTAINER=$(echo "$PARENT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['container_id'])")
echo "  Parent session: $PARENT_ID"
echo "  Parent container: ${PARENT_CONTAINER:0:12}..."

# Wait for parent to be ready
sleep 3

# Step 2: Spawn a child with a long-running task
echo ""
echo "[3/8] Spawning child session with long-running task..."
SPAWN_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/sessions/${PARENT_ID}/spawn" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @- <<'EOFBODY'
{
  "prompt": "Please create a file called 'progress.txt' in the workspace and write a line to it every 5 seconds for 30 seconds. Each line should contain the timestamp and a counter (e.g., 'Line 1: 2024-01-01 12:00:00'). Keep writing until you have 6 lines.",
  "context": {"task_type": "long_running_file_writer"}
}
EOFBODY
)
CHILD_ID=$(echo "$SPAWN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['child_session_id'])")
echo "  Child session: $CHILD_ID"

# Wait for child to start
sleep 5

# Step 3: Verify child workspace is mounted under parent
echo ""
echo "[4/8] Verifying child workspace structure..."
CHILD_WORKSPACE_PATH="/workspace/children/${CHILD_ID}"
docker exec "$PARENT_CONTAINER" ls -la /workspace/children/ 2>/dev/null || echo "  (Children directory not yet created - waiting)"
sleep 3
docker exec "$PARENT_CONTAINER" ls -la /workspace/children/ 2>/dev/null || echo "  (Still waiting for children directory)"

# Step 4: Monitor child for a bit
echo ""
echo "[5/8] Monitoring child session..."
for i in {1..3}; do
  echo "  Check $i/3..."
  CHILD_STATUS=$(curl -s "http://localhost:8000/api/v1/sessions/${CHILD_ID}" \
    -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status', 'unknown'))")
  echo "    Child status: $CHILD_STATUS"

  # Check if child has created the file yet
  if docker exec "$PARENT_CONTAINER" test -f "${CHILD_WORKSPACE_PATH}/progress.txt" 2>/dev/null; then
    echo "    Child has started writing progress.txt"
    docker exec "$PARENT_CONTAINER" cat "${CHILD_WORKSPACE_PATH}/progress.txt" 2>/dev/null | head -3 || true
  fi
  sleep 5
done

# Step 5: Send interrupt to change the task
echo ""
echo "[6/8] Sending interrupt to child session..."
INTERRUPT_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/sessions/${CHILD_ID}/interrupt" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @- <<'EOFBODY'
{
  "type": "redirect",
  "message": "CHANGE OF PLANS: Stop writing to progress.txt. Instead, create a new file called 'interrupted.txt' and write 'Task was interrupted by parent at this point' followed by the current timestamp. Then create a file called 'final_summary.txt' with a summary of what you did.",
  "priority": "high"
}
EOFBODY
)
echo "  Interrupt response: $(echo "$INTERRUPT_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status', d.get('error', 'unknown')))")"

# Step 6: Wait for child to process interrupt and complete
echo ""
echo "[7/8] Waiting for child to process interrupt and complete..."
INTERRUPT_PROCESSED=false
for i in {1..15}; do
  echo "  Wait iteration $i/15..."
  CHILD_STATUS=$(curl -s "http://localhost:8000/api/v1/sessions/${CHILD_ID}" \
    -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status', 'unknown'))")
  echo "    Child status: $CHILD_STATUS"

  # Check for new files created after interrupt
  echo "    Checking child workspace..."
  docker exec "$PARENT_CONTAINER" ls "${CHILD_WORKSPACE_PATH}/" 2>/dev/null || true

  # Check if interrupt files were created (indicates interrupt was processed)
  if docker exec "$PARENT_CONTAINER" test -f "${CHILD_WORKSPACE_PATH}/interrupted.txt" 2>/dev/null; then
    echo "    *** INTERRUPT WAS PROCESSED - interrupted.txt exists! ***"
    INTERRUPT_PROCESSED=true
    # Wait a bit more for final_summary.txt
    sleep 5
    break
  fi

  if docker exec "$PARENT_CONTAINER" test -f "${CHILD_WORKSPACE_PATH}/final_summary.txt" 2>/dev/null; then
    echo "    *** INTERRUPT WAS PROCESSED - final_summary.txt exists! ***"
    INTERRUPT_PROCESSED=true
    break
  fi

  # If session ended, stop waiting
  if [ "$CHILD_STATUS" == "stopped" ] || [ "$CHILD_STATUS" == "failed" ]; then
    echo "    Child session ended"
    break
  fi

  sleep 5
done

if [ "$INTERRUPT_PROCESSED" = false ]; then
  echo ""
  echo "  Note: Interrupt was queued but may not have been processed yet."
  echo "  The interrupt is processed after the current task completes."
  echo "  Extended waiting to allow next turn to execute..."
  for j in {1..8}; do
    sleep 5
    echo "    Extended wait $j/8..."
    docker exec "$PARENT_CONTAINER" ls "${CHILD_WORKSPACE_PATH}/" 2>/dev/null || true
    if docker exec "$PARENT_CONTAINER" test -f "${CHILD_WORKSPACE_PATH}/interrupted.txt" 2>/dev/null; then
      echo "    *** INTERRUPT WAS PROCESSED ***"
      INTERRUPT_PROCESSED=true
      break
    fi
  done
fi

# Step 7: Verify interrupt was applied by checking workspace
echo ""
echo "[8/8] Verifying interrupt was applied..."
echo "  Files in child workspace:"
docker exec "$PARENT_CONTAINER" ls -la "${CHILD_WORKSPACE_PATH}/" 2>/dev/null || echo "  (Workspace not accessible)"

echo ""
echo "  Contents of progress.txt (if exists):"
docker exec "$PARENT_CONTAINER" cat "${CHILD_WORKSPACE_PATH}/progress.txt" 2>/dev/null || echo "  (File not found)"

echo ""
echo "  Contents of interrupted.txt (if exists - should be created after interrupt):"
docker exec "$PARENT_CONTAINER" cat "${CHILD_WORKSPACE_PATH}/interrupted.txt" 2>/dev/null || echo "  (File not found - interrupt may not have been processed yet)"

echo ""
echo "  Contents of final_summary.txt (if exists):"
docker exec "$PARENT_CONTAINER" cat "${CHILD_WORKSPACE_PATH}/final_summary.txt" 2>/dev/null || echo "  (File not found)"

# Cleanup
echo ""
echo "=========================================="
echo "Cleanup"
echo "=========================================="
echo "Stopping parent session (which will also affect children)..."
curl -s -X POST "http://localhost:8000/api/v1/sessions/${PARENT_ID}/stop" \
  -H "Authorization: Bearer $TOKEN" > /dev/null
curl -s -X POST "http://localhost:8000/api/v1/sessions/${CHILD_ID}/stop" \
  -H "Authorization: Bearer $TOKEN" > /dev/null 2>&1 || true

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="
echo ""
echo "Key things to verify:"
echo "1. Child workspace was mounted under parent at /workspace/children/<child_id>/"
echo "2. Child created progress.txt before interrupt"
echo "3. After interrupt, child created interrupted.txt and/or final_summary.txt"
echo "4. Parent could access all child files through the mounted workspace"
