from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'KYSSCHECK'
    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_algorithm: str = 'HS256'
    jwt_access_ttl_minutes: int = 20
    registration_token: str
    allowed_commands: str = 'uptime,df -h,free -m'
    allowed_task_types: str = 'check_cpu,check_ram,check_disk,check_ports,check_system_info,run_command'
    cors_origins: str = 'http://localhost:8000'
    enforce_https: bool = True
    agent_offline_seconds: int = 25

    @property
    def allowed_command_set(self) -> set[str]:
        return {c.strip() for c in self.allowed_commands.split(',') if c.strip()}

    @property
    def allowed_task_type_set(self) -> set[str]:
        return {c.strip() for c in self.allowed_task_types.split(',') if c.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [c.strip() for c in self.cors_origins.split(',') if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
