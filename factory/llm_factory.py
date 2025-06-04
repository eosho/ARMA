import os
from typing import Literal
from .config import config
class LLMFactory:
    """
    Factory class to return a LangChain LLM instance based on environment variables.
    """
    def __init__(self):
        self.llm = self.get_llm()

    @staticmethod
    def get_llm(provider: Literal["openai", "azure"] = "azure"):
        """
        Factory function to return a LangChain LLM instance based on environment variables.
        Supports 'openai' and 'azure' as LLM providers.
        
        It uses the config.py file to get the LLM client.

        Args:
            provider (str): The LLM provider to use.
        Returns:
            A LangChain LLM instance of the specified provider.
        """
        if provider == "openai":
            return config.get_openai_client()
        elif provider == "azure":
            return config.get_azure_openai_client()
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
