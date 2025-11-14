"""LLM registry for the deployment agent."""

from typing import Any

from langchain_openai import AzureChatOpenAI

from arma.core.config import get_settings


def get_llm(**kwargs: Any) -> AzureChatOpenAI:
    """Get configured Azure OpenAI LLM instance.

    Args:
        **kwargs: Override configuration (temperature, azure_deployment, streaming, etc.)

    Returns:
        Configured AzureChatOpenAI instance
    """
    settings = get_settings()

    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        raise ValueError("Azure OpenAI endpoint and API key required")

    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        openai_api_key=settings.azure_openai_api_key,  # type: ignore[arg-type]
        api_version=kwargs.get("api_version", settings.azure_openai_api_version),
        azure_deployment=kwargs.get(
            "azure_deployment", settings.azure_openai_deployment_name or "gpt-4o"
        ),
        temperature=kwargs.get("temperature", 0.0),
        streaming=kwargs.get("streaming", False),
    )
