from pydantic_settings import SettingsConfigDict, BaseSettings

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__", env_file=".env", env_file_encoding="latin-1", extra="ignore")

    openai_bobobidou_key: str = ""
    openai_instaposter_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    insta_client_id: str = ""
    insta_client_secret: str = ""
    auth_redirect_uri: str = ""
    google_auth_url: str = ""
    insta_auth_url: str = ""
    google_token_url: str = ""
    insta_token_url: str = ""
    google_user_info_url: str = ""
    insta_graph_api: str = ""
    insta_refresh_token_url: str = ""
    secret_key: str = ""
    algorithm: str = ""
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    insta_long_lived_token_url:str = ""
    database_url: str = ""
    openfigi_api_key: str = ""
    openai_investment_key: str = ""
    web_frontend_url: str = "http://localhost:5173"


settings = Settings()