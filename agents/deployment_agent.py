"""
This agent is responsible for deploying (create/update) Azure resources using ARM templates.
It uses tools and a ReAct agent to decide how to deploy and to handle missing/invalid fields.
Supports both resource group and subscription-scope deployments.
"""

import logging
import json
from datetime import datetime
from langgraph.prebuilt import create_react_agent
from state import ARMAState
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from langgraph.types import interrupt
from factory.llm_factory import LLMFactory
from langchain_core.tools import tool
from prompts import DEPLOYMENT_SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# --- Tool 1: Deploy at Resource Group Scope ---
"""
This tool deploys the ARM template to a resource group (resourceGroup scope).
It uses the Azure SDK to deploy the template.
"""
@tool
def deploy_resource_group_scope_tool(subscription_id=None, resource_group_name=None, template=None, parameter_file_content=None, location=None, messages=None, **kwargs):
    """
    Deploys the ARM template to a resource group (resourceGroup scope).
    
    Args:
        subscription_id (str): The subscription ID.
        resource_group_name (str): The resource group name.
        template (dict): The ARM template.
        parameter_file_content (dict): The parameter file content.
        location (str): The location.
        messages (list): The list of messages to pass to the LLM.
        **kwargs: Additional keyword arguments.
    """
    parameters = (parameter_file_content or {}).get("parameters", {})
    if not (subscription_id and resource_group_name and template and parameters):
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Missing required fields for resource group deployment."}],
            "deployment_status": "failed",
            "deployment_error": "Missing required fields for resource group deployment."
        }
    try:
        credential = DefaultAzureCredential()
        client = ResourceManagementClient(credential, subscription_id)
        deployment_name = f"ai-deployment-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        t = template
        if isinstance(t, str):
            t = json.loads(t)
        logger.info(f"Deploying template to resource group {resource_group_name} in subscription {subscription_id}")
        poller = client.deployments.begin_create_or_update(
            resource_group_name,
            deployment_name,
            {
                "properties": {
                    "mode": "Incremental",
                    "template": t,
                    "parameters": parameters
                }
            }
        )
        result = poller.result()
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Resource group deployment succeeded."}],
            "deployment_result": result.as_dict() if hasattr(result, "as_dict") else str(result),
            "deployment_status": "success"
        }
    except Exception as e:
        logger.error(f"Resource group deployment failed: {e}")
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": f"Resource group deployment failed: {e}"}],
            "deployment_result": None,
            "deployment_error": str(e),
            "deployment_status": "failed"
        }

# --- Tool 2: Deploy at Subscription Scope ---
"""
This tool deploys the ARM template at the subscription scope (subscription scope).
It uses the Azure SDK to deploy the template.
"""
@tool
def deploy_subscription_scope_tool(subscription_id=None, template=None, parameter_file_content=None, location=None, messages=None, **kwargs):
    """
    Deploys the ARM template at the subscription scope (subscription scope).
    
    Args:
        subscription_id (str): The subscription ID.
        template (dict): The ARM template.
        parameter_file_content (dict): The parameter file content.
        location (str): The location.
        messages (list): The list of messages to pass to the LLM.
        **kwargs: Additional keyword arguments.
    """
    parameters = (parameter_file_content or {}).get("parameters", {})
    if not (subscription_id and template and parameters and location):
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Missing required fields for subscription deployment."}],
            "deployment_status": "failed",
            "deployment_error": "Missing required fields for subscription deployment."
        }
    try:
        credential = DefaultAzureCredential()
        client = ResourceManagementClient(credential, subscription_id)
        deployment_name = f"ai-deployment-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        t = template
        if isinstance(t, str):
            t = json.loads(t)
        logger.info(f"Deploying template at subscription scope in subscription {subscription_id}, location {location}")
        poller = client.deployments.begin_create_or_update_at_subscription_scope(
            deployment_name,
            {
                "location": location,
                "properties": {
                    "mode": "Incremental",
                    "template": t,
                    "parameters": parameters
                }
            }
        )
        result = poller.result()
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Subscription scope deployment succeeded."}],
            "deployment_result": result.as_dict() if hasattr(result, "as_dict") else str(result),
            "deployment_status": "success"
        }
    except Exception as e:
        logger.error(f"Subscription scope deployment failed: {e}")
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": f"Subscription scope deployment failed: {e}"}],
            "deployment_result": None,
            "deployment_error": str(e),
            "deployment_status": "failed"
        }

# --- Tool 3: Prompt for Missing/Invalid Fields ---
"""
This tool prompts the user for missing or invalid fields for deployment.
It raises an interrupt to stop the agent.
"""
@tool
def prompt_for_missing_deploy_tool(deployment_error=None, messages=None, **kwargs):
    """
    Prompts the user for missing or invalid fields for deployment.
    
    Args:
        deployment_error (str): The error message.
        messages (list): The list of messages to pass to the LLM.
        **kwargs: Additional keyword arguments.
    """
    msg = deployment_error or "Missing or invalid fields for deployment."
    updated_messages = list(messages) if messages else []
    updated_messages.append({"role": "system", "content": msg})
    raise interrupt(msg)

# --- Build ReAct Agent ---
"""
This function builds the ReAct agent for deployment.
It uses the tools defined above.
"""
def build_deployment_agent():
    llm = LLMFactory.get_llm()
    tools = [
        deploy_resource_group_scope_tool,
        deploy_subscription_scope_tool,
        prompt_for_missing_deploy_tool,
    ]
    agent = create_react_agent(
        tools=tools,
        model=llm,
        state_schema=ARMAState,
        prompt=DEPLOYMENT_SYSTEM_PROMPT,
        name="deployment_agent"
    )
    return agent
