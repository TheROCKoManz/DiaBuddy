#!/bin/bash
set -e

echo "Starting FastAPI..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

echo "Starting Streamlit..."
streamlit run frontend/streamlit_app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.headless=true &

echo "Waiting for Streamlit to be ready..."
until bash -c 'echo > /dev/tcp/localhost/8501' 2>/dev/null; do sleep 0.5; done
echo "Streamlit is up."

echo "Starting nginx..."
nginx -g 'daemon off;' &

# Wait for all background processes; exit if any one dies
wait -n
echo "A process exited. Shutting down."
exit 1