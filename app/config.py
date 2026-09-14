from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    supabase_url: str
    supabase_service_role_key: str
    owner_telegram_id: int
    timezone: str = "Asia/Tashkent"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
