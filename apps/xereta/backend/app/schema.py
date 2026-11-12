"""Generate the frontend contract without connecting to runtime services."""
import json
import secrets

from app.config import Settings
from app.main import create_app

if __name__ == "__main__":
    settings = Settings(database_url="sqlite://", secret_key=secrets.token_urlsafe(48),
        owner_password=secrets.token_urlsafe(32), agent_read_token=secrets.token_urlsafe(48))
    print(json.dumps(create_app(settings).openapi(), ensure_ascii=False))
