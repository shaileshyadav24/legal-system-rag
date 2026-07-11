#!/bin/bash

# Auth service (port 8001)
AUTH_URL="http://localhost:8001"
# Chat service (port 8000) - a token from the auth service works here directly
CHAT_URL="http://localhost:8000"

# Register (returns an access_token) - or use /auth/login if you already have an account
TOKEN=$(curl -s -X POST "$AUTH_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "jane@example.com", "password": "hunter2", "full_name": "Jane Doe"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Query across all collections, user (plain-language) role
curl -X POST "$CHAT_URL/query/user" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "I have run into accident, what can I do to avoid insurance fraud?"}'

# Query a specific collection (e.g., SCC), lawyer (precise legal) role
curl -X POST "$CHAT_URL/query/lawyer" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is the law regarding contracts?", "collection_name": "SCC"}'

# Follow-up question in the same conversation: pass back the session_id from
# the first response instead of resending history - the server loads it.
curl -X POST "$CHAT_URL/query/user" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What about a rear-end collision specifically?", "session_id": "<session_id from a previous response>"}'

# List this user's past conversations
curl "$CHAT_URL/chat/sessions" -H "Authorization: Bearer $TOKEN"

# Log out (revokes this token server-side)
curl -X POST "$AUTH_URL/auth/logout" -H "Authorization: Bearer $TOKEN"
