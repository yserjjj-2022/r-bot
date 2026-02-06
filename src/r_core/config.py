from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices

class Settings(BaseSettings):
    # App
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    
    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "rbot"
    DB_USER: str = "rbot"
    DB_PASSWORD: str = "rbot_password"
    
    # LLM (VseGPT / DeepSeek / OpenAI)
    # Support both OPENAI_API_KEY and VSEGPT_API_KEY
    OPENAI_API_KEY: str = Field(validation_alias=AliasChoices('OPENAI_API_KEY', 'VSEGPT_API_KEY'))
    OPENAI_BASE_URL: str = "https://api.vsegpt.ru/v1" # VseGPT default
    
    # Embeddings
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536
    
    # Personality Defaults
    DEFAULT_CHARACTER_ID: str = "default_rbot"

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
