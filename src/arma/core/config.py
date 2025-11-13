"""Core configuration management using Pydantic settings.

This module provides centralized configuration for the ARMA application,
loading settings from environment variables and .env files.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings.

    All settings can be overridden via environment variables.
    For example, DATABASE_URL env var will override database_url.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Azure Configuration
    azure_client_id: str | None = Field(
        default=None, description="Azure service principal client ID"
    )
    azure_client_secret: str | None = Field(
        default=None, description="Azure service principal secret"
    )
    azure_tenant_id: str | None = Field(default=None, description="Azure tenant ID")

    # Azure OpenAI Configuration
    azure_openai_endpoint: str = Field(default=..., description="Azure OpenAI endpoint URL")
    azure_openai_api_key: str = Field(default=..., description="Azure OpenAI API key")
    azure_openai_deployment_name: str | None = Field(
        default="gpt-4o-mini", description="Azure OpenAI deployment name"
    )
    azure_openai_api_version: str | None = Field(
        default="2024-08-01-preview", description="Azure OpenAI API version"
    )

    # LangSmith Configuration (optional)
    langsmith_api_key: str | None = Field(
        default=None, description="LangSmith API key for observability"
    )
    langsmith_project: str = Field(default="arma-dev", description="LangSmith project name")

    @field_validator("azure_openai_endpoint")
    @classmethod
    def validate_openai_endpoint(cls, v: str) -> str:
        """Validate Azure OpenAI endpoint format.

        Args:
            v: Endpoint URL to validate

        Returns:
            Validated endpoint URL

        Raises:
            ValueError: If endpoint format is invalid
        """
        if not v.startswith("https://"):
            raise ValueError("Azure OpenAI endpoint must use HTTPS")
        if not v.endswith("/"):
            v = f"{v}/"
        return v

    @property
    def use_managed_identity(self) -> bool:
        """Check if using Azure Managed Identity for authentication.

        Returns:
            True if managed identity (no explicit credentials), False otherwise
        """
        return not (self.azure_client_id and self.azure_client_secret and self.azure_tenant_id)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Uses LRU cache to ensure settings are loaded only once.

    Returns:
        Cached Settings instance
    """
    return Settings()


# Global settings instance
settings = get_settings()
