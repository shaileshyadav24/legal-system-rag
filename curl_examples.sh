#!/bin/bash

# Query across all collections (JSON body)
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"q": "I have run into accident, what can I do to avoid insurance fraud?"}'

# Query a specific collection (e.g., SCC) with JSON body
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"q": "What is the law regarding contracts?", "collection_name": "SCC"}'
