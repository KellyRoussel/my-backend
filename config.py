from pydantic_settings import SettingsConfigDict, BaseSettings

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__", env_file=".env")

    openai_bobobidou_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    google_auth_url: str = ""
    google_token_url: str = ""
    google_user_info_url: str = ""
    secret_key: str = ""
    algorithm: str = ""
    access_token_expire_minutes: int = 60


settings = Settings()