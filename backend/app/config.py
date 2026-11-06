from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', case_sensitive=False)
    app_env: str = 'development'
    db_host: str = 'localhost'
    db_port: int = 5432
    db_name: str = 'appdb'
    db_user: str = 'appuser'
    db_password: str = ''
    db_password_file: str = ''
    cookie_secure: bool = False
    allowed_origins: str = 'http://localhost:5173,http://localhost:8080'
    session_hours: int = 8
    reset_mode: str = 'disabled'
    demo_seed_enabled: bool = False
    demo_password: str = ''
    demo_user_email: str = 'assia.benkacem@example.org'
    demo_admin_email: str = 'youssef.amrani@example.org'

    @property
    def origins(self):
        return [s.strip().rstrip('/') for s in self.allowed_origins.split(',') if s.strip()]

    @property
    def database_url(self):
        password = Path(self.db_password_file).read_text().rstrip('\r\n') if self.db_password_file else self.db_password
        if not password:
            raise ValueError('DB_PASSWORD ou DB_PASSWORD_FILE est requis')
        return URL.create('postgresql+psycopg', username=self.db_user, password=password,
                          host=self.db_host, port=self.db_port, database=self.db_name)

    def validate_runtime(self):
        if self.app_env == 'production' and (not self.cookie_secure or self.reset_mode != 'disabled' or self.demo_seed_enabled):
            raise ValueError('Production : cookies Secure requis, seed et reset demo interdits')


@lru_cache
def settings():
    value = Settings()
    value.validate_runtime()
    return value
