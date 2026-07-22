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
JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    import secrets as _secrets
    JWT_SECRET = _secrets.token_hex(32)
    print(f"WARNING: No JWT_SECRET set. Generated ephemeral secret (tokens will invalidate on restart).")
    print(f"Set JWT_SECRET in .env for persistence.")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRATION_HOURS: int = int(os.environ.get("JWT_EXPIRATION_HOURS", "24"))

# Default admin credentials (used only on first DB init)
DEFAULT_ADMIN_USERNAME: str = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD: str = os.environ.get("DEFAULT_ADMIN_PASSWORD", "")
if not DEFAULT_ADMIN_PASSWORD:
    import secrets as _secrets2
    DEFAULT_ADMIN_PASSWORD = _secrets2.token_urlsafe(12)
    print(f"WARNING: No DEFAULT_ADMIN_PASSWORD set. Generated: {DEFAULT_ADMIN_PASSWORD}")
    print(f"Set DEFAULT_ADMIN_PASSWORD in .env for persistence.")

# Default API key (used only on first DB init)
DEFAULT_API_KEY: str = os.environ.get("DEFAULT_API_KEY", "")
if not DEFAULT_API_KEY:
    import secrets as _secrets3
    DEFAULT_API_KEY = "sk-gsdm-" + _secrets3.token_hex(24)
    print(f"WARNING: No DEFAULT_API_KEY set. Generated: {DEFAULT_API_KEY}")
    print(f"Set DEFAULT_API_KEY in .env for persistence.")
