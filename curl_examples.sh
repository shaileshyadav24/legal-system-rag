#!/bin/bash

# Query across all collections, user (plain-language) role
curl -X POST "http://localhost:8000/query/user" \
  -H "Content-Type: application/json" \
  -d '{"query": "I have run into accident, what can I do to avoid insurance fraud?"}'

# Query a specific collection (e.g., SCC), lawyer (precise legal) role
curl -X POST "http://localhost:8000/query/lawyer" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the law regarding contracts?", "collection_name": "SCC"}'

# Follow-up question using conversation history
curl -X POST "http://localhost:8000/query/user" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What about a rear-end collision specifically?",
    "history": [
      {"q": "I have run into accident, what can I do to avoid insurance fraud?", "answer": "Previous answer here"}
    ]
  }'
