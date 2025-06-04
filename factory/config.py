# app_config.py
import logging
import os
from typing import Optional
# from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from dotenv import load_dotenv

load_dotenv()

class AppConfig:
    """Application configuration class that loads settings from environment variables."""

    def __init__(self):
        """Initialize the application configuration with environment variables."""
        # Azure authentication settings
        self.AZURE_TENANT_ID = self._get_optional("AZURE_TENANT_ID")
        self.AZURE_CLIENT_ID = self._get_optional("AZURE_CLIENT_ID")
        self.AZURE_CLIENT_SECRET = self._get_optional("AZURE_CLIENT_SECRET")
        self.AZURE_SUBSCRIPTION_ID = self._get_optional("AZURE_SUBSCRIPTION_ID")

        # OpenAI settings
        self.OPENAI_API_KEY = self._get_optional("OPENAI_API_KEY")

        # CosmosDB settings
        # self.COSMOSDB_ENDPOINT = self._get_optional("COSMOSDB_ENDPOINT")
        # self.COSMOSDB_DATABASE = self._get_optional("COSMOSDB_DATABASE")
        # self.COSMOSDB_CONTAINER = self._get_optional("COSMOSDB_CONTAINER")

        # Azure OpenAI settings
        self.AZURE_OPENAI_DEPLOYMENT = self._get_required("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        self.AZURE_OPENAI_API_VERSION = self._get_required("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        self.AZURE_OPENAI_ENDPOINT = self._get_required("AZURE_OPENAI_ENDPOINT")
        self.AZURE_OPENAI_API_KEY = self._get_required("AZURE_OPENAI_API_KEY")

        # Cached clients and resources
        self._azure_credentials = None
        self._cosmos_client = None
        self._cosmos_database = None

    @staticmethod
    def _get_required(name: str, default: Optional[str] = None) -> str:
        """Get a required configuration value from environment variables.

        Args:
            name: The name of the environment variable
            default: Optional default value if not found

        Returns:
            The value of the environment variable or default if provided

        Raises:
            ValueError: If the environment variable is not found and no default is provided
        """
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            logging.warning(
                "Environment variable %s not found, using default value", name
            )
            return default
        raise ValueError(
            f"Environment variable {name} not found and no default provided"
        )

    @staticmethod
    def _get_optional(name: str, default: str = "") -> str:
        """Get an optional configuration value from environment variables.

        Args:
            name: The name of the environment variable
            default: Default value if not found (default: "")

        Returns:
            The value of the environment variable or the default value
        """
        if name in os.environ:
            return os.environ[name]
        return default

    def get_azure_credentials(self):
        """Get Azure credentials using DefaultAzureCredential.

        Returns:
            DefaultAzureCredential instance for Azure authentication
        """
        # Cache the credentials object
        if self._azure_credentials is not None:
            return self._azure_credentials

        try:
            self._azure_credentials = DefaultAzureCredential()
            return self._azure_credentials
        except Exception as exc:
            logging.warning("Failed to create DefaultAzureCredential: %s", exc)
            return None
        
    def get_resource_management_subscription_client(self):
        """Get a Resource Management client for the configured subscription.

        Returns:
            A Resource Management client
        """
        return SubscriptionClient(self.get_azure_credentials())
    
    def get_resource_management_client(self, subscription_id: str):
        """Get a Resource Management client for the configured resource group.

        Returns:
            A Resource Management client
        """
        return ResourceManagementClient(self.get_azure_credentials(), subscription_id)

    # def get_cosmos_database_client(self):
    #     """Get a Cosmos DB client for the configured database.

    #     Returns:
    #         A Cosmos DB database client
    #     """
    #     try:
    #         if self._cosmos_client is None:
    #             self._cosmos_client = CosmosClient(
    #                 self.COSMOSDB_ENDPOINT, credential=self.get_azure_credentials()
    #             )

    #         if self._cosmos_database is None:
    #             self._cosmos_database = self._cosmos_client.get_database_client(
    #                 self.COSMOSDB_DATABASE
    #             )

    #         return self._cosmos_database
    #     except Exception as exc:
    #         logging.error(
    #             "Failed to create CosmosDB client: %s. CosmosDB is required for this application.",
    #             exc,
    #         )
    #         raise

    def get_openai_client(self):
        """Get an OpenAI client for the configured API key.

        Returns:
            An OpenAI client
        """
        return ChatOpenAI(api_key=self.OPENAI_API_KEY)

    def get_azure_openai_client(self):
        """Get an Azure OpenAI client for the configured API key.

        Returns:
            An Azure OpenAI client
        """
        return AzureChatOpenAI(
            azure_deployment=self.AZURE_OPENAI_DEPLOYMENT,
            api_version=self.AZURE_OPENAI_API_VERSION,
            api_key=self.AZURE_OPENAI_API_KEY,
            model_name=self.AZURE_OPENAI_DEPLOYMENT,
            azure_endpoint=self.AZURE_OPENAI_ENDPOINT,
            streaming=True
        )

# Create a global instance of AppConfig
config = AppConfig()