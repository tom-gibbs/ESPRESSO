#!/bin/bash
cd "$(dirname "$0")"

# Start server in background
python3 run.py &
SERVER_PID=$!

# Wait for server to be ready (up to 10 seconds)
echo "Starting ESPRESSO server..."
for i in {1..20}; do
    if curl -s http://localhost:8000 > /dev/null 2>&1; then
        echo "Server ready!"
        open "http://localhost:8000/index.html"
        break
    fi
    sleep 0.5
done

# Keep terminal open and wait for server process
wait $SERVER_PID
