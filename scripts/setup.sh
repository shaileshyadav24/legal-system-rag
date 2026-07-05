#!/usr/bin/env bash
# Interactive first-run setup: local MongoDB cluster -> dataset ingestion -> run the API.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ENV_FILE=".env"
MONGO_CONTAINER_NAME="nextwork-mongodb-local"
MONGO_LOCAL_URI="mongodb://localhost:27017/?directConnection=true"

ask_yes_no() {
    local prompt="$1"
    local reply
    while true; do
        read -r -p "$prompt [y/n]: " reply
        case "$reply" in
            [Yy]|[Yy][Ee][Ss]) return 0 ;;
            [Nn]|[Nn][Oo]) return 1 ;;
            *) echo "Please answer y or n." ;;
        esac
    done
}

set_env_var() {
    local key="$1"
    local value="$2"
    touch "$ENV_FILE"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        # Portable in-place edit for both GNU and BSD sed.
        sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

# --- Step 1: local MongoDB cluster ---------------------------------------

echo
if ask_yes_no "Create a local MongoDB cluster (via Docker, mongodb-atlas-local) for testing?"; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "Docker is not installed or not on PATH. Install Docker first, then re-run this script." >&2
        exit 1
    fi

    if docker ps -a --format '{{.Names}}' | grep -qx "$MONGO_CONTAINER_NAME"; then
        if docker ps --format '{{.Names}}' | grep -qx "$MONGO_CONTAINER_NAME"; then
            echo "Container '$MONGO_CONTAINER_NAME' is already running."
        else
            echo "Starting existing container '$MONGO_CONTAINER_NAME'..."
            docker start "$MONGO_CONTAINER_NAME" >/dev/null
        fi
    else
        echo "Pulling and starting mongodb/mongodb-atlas-local as '$MONGO_CONTAINER_NAME'..."
        docker run -d -p 27017:27017 --name "$MONGO_CONTAINER_NAME" mongodb/mongodb-atlas-local >/dev/null
    fi

    echo "Waiting for MongoDB to accept connections on localhost:27017..."
    for i in $(seq 1 30); do
        if docker exec "$MONGO_CONTAINER_NAME" mongosh --quiet --eval "db.runCommand({ping:1})" >/dev/null 2>&1; then
            echo "MongoDB is ready."
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "MongoDB did not become ready in time. Check 'docker logs $MONGO_CONTAINER_NAME'." >&2
            exit 1
        fi
        sleep 2
    done

    set_env_var "MONGODB_URI" "$MONGO_LOCAL_URI"
    echo "MONGODB_URI written to $ENV_FILE ($MONGO_LOCAL_URI)."
else
    echo "Skipping local MongoDB setup - make sure MONGODB_URI in $ENV_FILE already points at a real Atlas cluster (Atlas Vector Search requires Atlas)."
fi

# Required config must be present explicitly - no silent defaults.
if [ ! -f "$ENV_FILE" ] || ! grep -q "^MONGODB_DB_NAME=" "$ENV_FILE" 2>/dev/null; then
    read -r -p "Enter MONGODB_DB_NAME: " db_name
    set_env_var "MONGODB_DB_NAME" "$db_name"
fi

if [ ! -f "$ENV_FILE" ] || ! grep -q "^JWT_SECRET=" "$ENV_FILE" 2>/dev/null; then
    read -r -p "Enter JWT_SECRET (leave blank to generate a random one): " jwt_secret
    if [ -z "$jwt_secret" ]; then
        jwt_secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
        echo "Generated JWT_SECRET: $jwt_secret"
    fi
    set_env_var "JWT_SECRET" "$jwt_secret"
fi

if [ ! -f "$ENV_FILE" ] || ! grep -q "^JWT_EXPIRE_MINUTES=" "$ENV_FILE" 2>/dev/null; then
    read -r -p "Enter JWT_EXPIRE_MINUTES [1440]: " jwt_expire
    jwt_expire="${jwt_expire:-1440}"
    set_env_var "JWT_EXPIRE_MINUTES" "$jwt_expire"
fi

# --- Step 2: dataset ingestion --------------------------------------------

echo
if ask_yes_no "Fetch and ingest the datasets into MongoDB now (dataset/dataset.py)?"; then
    if ask_yes_no "Install/refresh Python dependencies first (pip install -r requirements.txt)?"; then
        pip install -r requirements.txt
    fi
    echo "Running dataset ingestion - this downloads parquet files and embeds each chunk, so it can take a while..."
    python3 dataset/dataset.py
else
    echo "Skipping dataset ingestion. Note: queries will 404/204 until case_law_documents is populated."
fi

# --- Step 3: run the project ----------------------------------------------

echo
if ask_yes_no "Run the API now (uvicorn app:app --port 8000 --host 0.0.0.0)?"; then
    if ! command -v ollama >/dev/null 2>&1; then
        echo "ollama is not installed or not on PATH. Install it and run 'ollama pull tinyllama' first." >&2
        exit 1
    fi
    if ! ollama list | grep -q "tinyllama"; then
        echo "tinyllama model not found locally - pulling it now..."
        ollama pull tinyllama
    fi
    echo "Starting the API (Ctrl+C to stop)..."
    exec uvicorn app:app --port 8000 --host 0.0.0.0
else
    echo "Skipping API startup. Run it later with: uvicorn app:app --port 8000 --host 0.0.0.0"
fi
