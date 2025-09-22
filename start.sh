#!/bin/bash

# Debug script for Cloud Run deployment
echo "Starting Excel AI Agent Backend..."
echo "PORT environment variable: $PORT"
echo "HOST environment variable: $HOST"
echo "ENV environment variable: $ENV"

# Set default port if not provided
export PORT=${PORT:-8080}
echo "Using PORT: $PORT"

# Start the application
echo "Starting uvicorn server..."
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
