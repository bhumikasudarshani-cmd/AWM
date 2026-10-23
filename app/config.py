from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_app_id: str = ""
    github_private_key: str = ""
    github_webhook_secret: str = ""
    redis_url: str = "redis://localhost:6379"
    auth_mode: str = "mock"
    dump_fixtures: bool = False  # dev only: save raw PR file lists to ./fixtures_dump

    @property
    def private_key_pem(self) -> str:
        return self.github_private_key.replace("\\n", "\n")


settings = Settings()
