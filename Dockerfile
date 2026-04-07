FROM python:3.11-slim

# Install nginx
RUN apt-get update && apt-get install -y --no-install-recommends nginx && rm -rf /var/lib/apt/lists/*

WORKDIR /diabuddy

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install nginx config
COPY nginx.conf /etc/nginx/nginx.conf

RUN chmod +x start.sh

# Cloud Run routes external traffic to 8080; nginx listens here and
# reverse-proxies to FastAPI (:8000) and Streamlit (:8501) internally.
EXPOSE 8080

CMD ["./start.sh"]