"""Application configuration — reads from environment variables / .env file."""

import os
from pathlib import Path

# Load .env file if present
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# Database
DB_PATH: str = os.environ.get("DB_PATH", "router.db")

# JWT Authentication
JWT_SECRET: str = os.environ.get("JWT_SECRET", "change-this-secret-in-production")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRATION_HOURS: int = int(os.environ.get("JWT_EXPIRATION_HOURS", "24"))

# Default admin credentials (used only on first DB init)
DEFAULT_ADMIN_USERNAME: str = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD: str = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin")

# Default API key (used only on first DB init)
DEFAULT_API_KEY: str = os.environ.get("DEFAULT_API_KEY", "sk-gsdm-default-key-change-me")
