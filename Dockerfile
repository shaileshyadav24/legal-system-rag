FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install deps first so this layer stays cached across source-only changes
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY app.py ./
COPY services/ ./services/
COPY prompts/ ./prompts/

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
