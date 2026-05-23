from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    telegram_bot_token: str
    telegram_admin_chat_id: int
    telegram_lowkey_chat_id: int
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
