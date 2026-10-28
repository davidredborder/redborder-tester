from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"


class Settings(BaseSettings):
    # Target Platform
    target_host: str = "10.1.33.160"
    target_port: int = 443
    use_https: bool = True
    verify_ssl: bool = False

    # Web UI Credentials
    web_user: str = "admin"
    web_password: str = "DefaultPassw0rd!"

    # Backend SSH Credentials
    ssh_user: str = "root"
    ssh_password: str = "redborder"
    ssh_port: int = 22
    ssh_timeout: int = 10

    # Test Execution & Playwright
    headless: bool = True
    browser: str = "chromium"
    default_timeout_ms: int = 15000

    model_config = SettingsConfigDict(
        env_file=ENV_PATH if ENV_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def base_url(self) -> str:
        protocol = "https" if self.use_https else "http"
        # Only omit default standard ports for their respective schemes
        is_default_port = (self.use_https and self.target_port == 443) or (
            not self.use_https and self.target_port == 80
        )
        port_suffix = "" if is_default_port else f":{self.target_port}"
        return f"{protocol}://{self.target_host}{port_suffix}"

    @property
    def target_url(self) -> str:
        return self.base_url


settings = Settings()
