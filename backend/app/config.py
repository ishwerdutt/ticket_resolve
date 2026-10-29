from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://support_user:support_pass@localhost:5434/ai_support"
    OPENAI_API_KEY: str = "sk-placeholder"
    JWT_SECRET: str = "change-me-in-production"
    JWT_EXPIRY_HOURS: int = 24
    REFUND_AUTO_APPROVE_LIMIT: float = 1000.0  # INR
    AGENT_MAX_STEPS: int = 6
    MODEL_NAME: str = "gpt-4o"
    ENVIRONMENT: str = "development"


settings = Settings()
