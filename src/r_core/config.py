from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices

class Settings(BaseSettings):
    # App
    ENV: str = Field(default="dev")
    LOG_LEVEL: str = Field(default="INFO")
    
    # ✨ EVAL_MODE: When True, uses isolated test database
    EVAL_MODE: bool = Field(default=False, validation_alias=AliasChoices('RCORE_EVAL_MODE', 'EVAL_MODE'))
    
    # Database
    DB_HOST: str = Field(default="localhost")
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default="rbot")
    DB_USER: str = Field(default="rbot")
    DB_PASSWORD: str = Field(default="rbot_password")
    
    # ✨ Test Database (used when EVAL_MODE=True)
    TEST_DB_HOST: str = Field(default="localhost")
    TEST_DB_PORT: int = Field(default=5432)
    TEST_DB_NAME: str = Field(default="rbot_test")
    TEST_DB_USER: str = Field(default="rbot")
    TEST_DB_PASSWORD: str = Field(default="rbot_password")
    
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
    
    # Debug / Logging
    ENABLE_LLM_RAW_LOGGING: bool = Field(default=False)  # По умолчанию выключено

    @property
    def database_url(self) -> str:
        """Returns the appropriate database URL based on EVAL_MODE."""
        if self.EVAL_MODE:
            return self.test_database_url
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def test_database_url(self) -> str:
        """Returns the test database URL."""
        return f"postgresql+asyncpg://{self.TEST_DB_USER}:{self.TEST_DB_PASSWORD}@{self.TEST_DB_HOST}:{self.TEST_DB_PORT}/{self.TEST_DB_NAME}"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
