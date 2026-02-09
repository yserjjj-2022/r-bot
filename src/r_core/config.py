from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices

class Settings(BaseSettings):
    # App
    ENV: str = Field(default="dev")
    LOG_LEVEL: str = Field(default="INFO")
    
    # Database
    DB_HOST: str = Field(default="localhost")
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default="rbot")
    DB_USER: str = Field(default="rbot")
    DB_PASSWORD: str = Field(default="rbot_password")
    
    # LLM (VseGPT / DeepSeek / OpenAI)
    OPENAI_API_KEY: str = Field(validation_alias=AliasChoices('OPENAI_API_KEY', 'VSEGPT_API_KEY'))
    OPENAI_BASE_URL: str = Field(
        default="https://api.vsegpt.ru/v1",
        validation_alias=AliasChoices('OPENAI_BASE_URL', 'VSEGPT_BASE_URL')
    )
    
    # Model Selection - читаем из .env, поддержка нескольких имён переменных
    LLM_MODEL_NAME: str = Field(
        default="deepseek/deepseek-chat-3.1-alt",
        validation_alias=AliasChoices('LLM_MODEL_NAME', 'LLM_MODEL_MAIN')
    )

    # Embeddings
    EMBEDDING_MODEL: str = Field(
        default="emb-openai/text-embedding-3-small",
        validation_alias=AliasChoices('EMBEDDING_MODEL', 'LLM_MODEL_EMBEDDING')
    )
    EMBEDDING_DIM: int = Field(default=1536)
    
    # Personality Defaults
    DEFAULT_CHARACTER_ID: str = Field(default="default_rbot")
    
    # Pool Settings (Crucial for Async)
    DB_POOL_SIZE: int = Field(default=5)
    DB_MAX_OVERFLOW: int = Field(default=10)

    @property
    def database_url(self) -> str:
        # Use asyncpg driver
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
