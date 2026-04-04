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
    allowed_task_types: str = 'check_cpu,check_ram,check_disk,check_ports,check_system_info,run_command,check_cpu_advanced,check_memory_advanced,check_disk_advanced,check_processes_top,check_uptime_reboot,check_network_reachability,check_ports_latency,check_dns,check_traceroute_basic,check_services_status,check_http_endpoint,check_database_connectivity,check_security_baseline,system_snapshot,system_snapshot_diff,check_logs_keywords,check_paths_sizes'
    cors_origins: str = 'http://localhost:8000'
    enforce_https: bool = True
    agent_offline_seconds: int = 25
    task_execution_timeout_seconds: int = 30

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
