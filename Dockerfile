# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/bun.lock* frontend/package-lock.json* ./
RUN npm install --legacy-peer-deps && npm install react-is
COPY frontend/ .
RUN npm run build

# Stage 2: Final image — Python slim with nginx
FROM python:3.12-slim AS runtime

# Install nginx and curl (for healthcheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx curl && \
    rm -rf /var/lib/apt/lists/* && \
    rm -f /etc/nginx/sites-enabled/default

# Create non-root user
RUN groupadd -g 1001 gsdm && \
    useradd -u 1001 -g gsdm -m -s /bin/sh gsdm

# Backend dependencies
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt python-multipart && \
    rm -rf /root/.cache

# Backend source
COPY backend/ ./backend/
RUN rm -rf backend/venv backend/__pycache__ backend/tests backend/*.db backend/.env

# Frontend static files
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

# Nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Data directory for SQLite (persistent volume mount point)
RUN mkdir -p /app/data && chown gsdm:gsdm /app/data

# Permissions
RUN chown -R gsdm:gsdm /app && \
    chown -R gsdm:gsdm /var/log/nginx && \
    chown -R gsdm:gsdm /var/lib/nginx && \
    chown -R gsdm:gsdm /run

# Startup script
RUN cat > /app/start.sh << 'EOF'
#!/bin/sh
set -e
cd /app/backend
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --log-level warning &
nginx -g "daemon off;"
EOF
RUN chmod +x /app/start.sh

# Environment defaults
ENV DB_PATH=/app/data/router.db
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root
USER gsdm

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:80/health || exit 1

CMD ["/app/start.sh"]
