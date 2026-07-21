# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/bun.lock* frontend/package-lock.json* ./
RUN npm install --legacy-peer-deps

COPY frontend/ .
RUN npm run build

# Stage 2: Final image with Python + Nginx
FROM python:3.12-slim

# Install nginx and supervisor
RUN apt-get update && apt-get install -y --no-install-recommends nginx supervisor && rm -rf /var/lib/apt/lists/*

# Backend
WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt python-multipart

COPY backend/ .
RUN rm -rf venv/ __pycache__/ tests/ *.db .env

# Frontend static files
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

# Nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -f /etc/nginx/sites-enabled/default

# Supervisor config
RUN cat > /etc/supervisor/conf.d/gsdm-r.conf << 'EOF'
[supervisord]
nodaemon=true
logfile=/dev/null
logfile_maxbytes=0

[program:backend]
command=uvicorn main:app --host 127.0.0.1 --port 8000
directory=/app/backend
autostart=true
autorestart=true
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0

[program:nginx]
command=nginx -g "daemon off;"
autostart=true
autorestart=true
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0
EOF

# Data volume for SQLite
RUN mkdir -p /app/data
ENV DB_PATH=/app/data/router.db

EXPOSE 80

CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
