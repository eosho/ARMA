import os
from langchain_openai import ChatOpenAI, AzureChatOpenAI

class LLMFactory:
    """
    Factory class to return a LangChain LLM instance based on environment variables.
    """
    def __init__(self):
        self.llm = self.get_llm()

    @staticmethod
    def get_llm():
        """
        Factory function to return a LangChain LLM instance based on environment variables.
        Supports 'openai' and 'azure' as LLM providers.
        
        Set LLM_PROVIDER to 'openai' or 'azure' in your environment.
        """
        provider = os.environ.get("LLM_PROVIDER", "azure").lower()
        if provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY must be set for OpenAI provider.")
            return ChatOpenAI(
                openai_api_key=api_key
            )
        elif provider == "azure":
            api_key = os.environ.get("AZURE_OPENAI_API_KEY")
            endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
            deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
            api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
            if not all([api_key, endpoint, deployment, api_version]):
                raise ValueError("AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, and AZURE_OPENAI_API_VERSION must be set for Azure provider.")
            return AzureChatOpenAI(
                azure_deployment=deployment,
                api_version=api_version,
                api_key=api_key,
                model_name=deployment,
                azure_endpoint=endpoint,
                streaming=True,
            )
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
