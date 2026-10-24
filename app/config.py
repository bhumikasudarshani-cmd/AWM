from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_app_id: str = ""
    github_private_key: str = ""
    github_webhook_secret: str = ""
    redis_url: str = "redis://localhost:6379"
    auth_mode: str = "mock"
    dump_fixtures: bool = False  # dev only: save raw PR file lists to ./fixtures_dump
    llm_base_url: str = ""  # empty = AI stage off
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout: float = 600.0
    llm_max_input_tokens: int = 5000
    llm_max_calls: int = 4

    @property
    def private_key_pem(self) -> str:
        return self.github_private_key.replace("\\n", "\n")


settings = Settings()
