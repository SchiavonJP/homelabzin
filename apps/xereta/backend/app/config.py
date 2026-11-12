from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="XERETA_", env_file=None)
    database_url: str
    secret_key: SecretStr = Field(min_length=32)
    owner_email: str = "owner@xereta.local"
    owner_password: SecretStr = Field(min_length=14)
    agent_read_token: SecretStr = Field(min_length=32)
    state_path: Path = Path("/data")
    silverbullet_url: str = "http://192.168.0.12:3011"
    silverbullet_token: SecretStr = SecretStr("")
    public_silverbullet_url: str = "https://silverbullet.joaopaulo.me"
    hindsight_url: str = "http://127.0.0.1:8888"
    hindsight_bank: str = "knowledge-vault-pilot"
    hindsight_token: SecretStr = SecretStr("")
    affine_reader_url: str = 'http://192.168.0.221:3012'
    affine_reader_token: SecretStr = SecretStr('')
    affine_workspaces: list[str] = []
    affine_imports: dict[str, str] = {}
    litellm_url: str = "http://192.168.0.211:4000/v1/chat/completions"
    litellm_key: SecretStr = SecretStr("")
    litellm_model: str = Field(default='generalist', pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    karakeep_url: str = 'http://192.168.0.12:3000'
    karakeep_token: SecretStr = SecretStr('')
    public_karakeep_url: str = 'https://keep.joaopaulo.me'
    library_enabled: bool = False
    article_domains: list[str] = []

    @field_validator('karakeep_url')
    @classmethod
    def karakeep_destination(cls, value):
        return validate_origin(value, {'192.168.0.12:3000', 'keep.joaopaulo.me'})

    @field_validator('public_karakeep_url')
    @classmethod
    def karakeep_public(cls, value):
        return validate_origin(value, {'keep.joaopaulo.me'})
    publish_enabled: bool = False
    acceptance_passed: bool = False
    session_hours: int = Field(default=8, ge=1, le=24)
    pilot_paths: list[str] = ["space/Homelab/Comandos.md", "space/Homelab/Ideas.md",
                             "space/AI assets/models notes/Agentics models.md"]

    @field_validator("silverbullet_url")
    @classmethod
    def silverbullet_destination(cls, value):
        return validate_origin(value, {"192.168.0.12:3011", "silverbullet.joaopaulo.me"})

    @field_validator("public_silverbullet_url")
    @classmethod
    def silverbullet_public(cls, value):
        return validate_origin(value, {"silverbullet.joaopaulo.me"})

    @field_validator("hindsight_url")
    @classmethod
    def hindsight_destination(cls, value):
        return validate_origin(value, {"127.0.0.1:8888", "localhost:8888", "sb_hindsight_pilot:8888"})

    @field_validator('affine_reader_url')
    @classmethod
    def affine_destination(cls, value):
        return validate_origin(value, {'192.168.0.221:3012', '127.0.0.1:3012'})

    @field_validator("litellm_url")
    @classmethod
    def gateway_destination(cls, value):
        parsed = urlsplit(value)
        if parsed.path != "/v1/chat/completions":
            raise ValueError("invalid_gateway_path")
        validate_origin(value.removesuffix(parsed.path), {"192.168.0.211:4000"})
        return value

    @field_validator("hindsight_bank")
    @classmethod
    def bank_name(cls, value):
        if not value.startswith("knowledge-vault-") or not all(c.isalnum() or c == "-" for c in value):
            raise ValueError("isolated_vault_bank_required")
        return value


def validate_origin(value, hosts):
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or parsed.netloc not in hosts
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        raise ValueError("destination_not_allowed")
    return value.rstrip("/")
