"""
This agent is responsible for performing actions on Azure resources: get, list, or delete.
It uses tools and a ReAct agent to decide which action to take and to handle missing/invalid fields.
"""

import logging
import json
from langgraph.prebuilt import create_react_agent
from state import ARMAState
from langgraph.types import interrupt
from factory import (
    LLMFactory,
    config
)
from langchain_core.tools import tool
from prompts import RESOURCE_ACTION_SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress logging for azure sdk
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("azure.core").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)
logging.getLogger("azure.mgmt.resource").setLevel(logging.WARNING)

# --- Tool 1: Get Resource ---
"""
This tool gets details of the specified Azure resource.
It uses the Azure SDK to get the resource.
"""
@tool
def get_resource_tool(subscription_id=None, resource_group_name=None, resource_type=None, provided_fields=None, messages=None, **kwargs):
    """
    Gets details of the specified Azure resource.
    
    Args:
        subscription_id (str): The subscription ID.
        resource_group_name (str): The resource group name.
        resource_type (str): The resource type.
    """
    resource_name = (provided_fields or {}).get("name")
    if not (subscription_id and resource_group_name and resource_type and resource_name):
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Missing required fields for get operation."}],
            "resource_action_status": "failed",
            "resource_action_error": "Missing required fields for get operation."
        }
    try:
        client = config.get_resource_management_client(subscription_id)
        namespace, type_name = resource_type.split("/", 1)
        api_version = "2021-04-01"
        logger.info(f"Getting resource: {resource_type} name={resource_name} rg={resource_group_name} sub={subscription_id}")
        resource = client.resources.get(
            resource_group_name=resource_group_name,
            resource_provider_namespace=namespace,
            parent_resource_path="",
            resource_type=type_name,
            resource_name=resource_name,
            api_version=api_version
        )
        resource_dict = resource.as_dict() if hasattr(resource, "as_dict") else resource
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Resource details fetched."}],
            "resource_action_result": resource_dict,
            "resource_action_status": "success"
        }
    except Exception as e:
        logger.error(f"Get resource failed: {e}")
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": f"Get resource failed: {e}"}],
            "resource_action_result": None,
            "resource_action_error": str(e),
            "resource_action_status": "failed"
        }

# --- Tool 2: List Resources ---
"""
This tool lists resources of the specified type in the given resource group. If resource_type is not provided, lists all resources in the resource group.
"""
@tool
def list_resources_tool(subscription_id=None, resource_group_name=None, resource_type=None, messages=None, **kwargs):
    """
    Lists resources of the specified type in the given resource group. If resource_type is not provided, lists all resources in the resource group.
    
    Args:
        subscription_id (str): The subscription ID.
        resource_group_name (str): The resource group name.
        resource_type (str, optional): The resource type. If None, lists all resources.
    """
    if not (subscription_id and resource_group_name):
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Missing required fields for list operation."}],
            "resource_action_status": "failed",
            "resource_action_error": "Missing required fields for list operation."
        }
    try:
        client = config.get_resource_management_client(subscription_id)
        if resource_type:
            namespace, type_name = resource_type.split("/", 1)
            filter_str = f"resourceType eq '{namespace}/{type_name}'"
            resources = client.resources.list_by_resource_group(
                resource_group_name=resource_group_name,
                filter=filter_str
            )
        else:
            resources = client.resources.list_by_resource_group(
                resource_group_name=resource_group_name
            )
        resource_list = [r.as_dict() if hasattr(r, "as_dict") else r for r in resources]
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Resources listed."}],
            "resource_action_result": resource_list,
            "resource_action_status": "success"
        }
    except Exception as e:
        logger.error(f"List resources failed: {e}")
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": f"List resources failed: {e}"}],
            "resource_action_result": None,
            "resource_action_error": str(e),
            "resource_action_status": "failed"
        }

# --- Tool 3: Delete Resource ---
"""
This tool deletes the specified Azure resource.
It uses the Azure SDK to delete the resource.
"""
@tool
def delete_resource_tool(subscription_id=None, resource_group_name=None, resource_type=None, provided_fields=None, messages=None, **kwargs):
    """
    Deletes the specified Azure resource.
    
    Args:
        subscription_id (str): The subscription ID.
        resource_group_name (str): The resource group name.
        resource_type (str): The resource type.
    """
    resource_name = (provided_fields or {}).get("name")
    if not (subscription_id and resource_group_name and resource_type and resource_name):
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Missing required fields for delete operation."}],
            "resource_action_status": "failed",
            "resource_action_error": "Missing required fields for delete operation."
        }
    try:
        client = config.get_resource_management_client(subscription_id)
        namespace, type_name = resource_type.split("/", 1)
        api_version = "2021-04-01"
        logger.info(f"Deleting resource: {resource_type} name={resource_name} rg={resource_group_name} sub={subscription_id}")
        delete_poller = client.resources.begin_delete(
            resource_group_name=resource_group_name,
            resource_provider_namespace=namespace,
            parent_resource_path="",
            resource_type=type_name,
            resource_name=resource_name,
            api_version=api_version
        )
        delete_result = delete_poller.result()
        if delete_result is not None:
            result_dict = delete_result.as_dict() if hasattr(delete_result, "as_dict") else delete_result
            result_msg = result_dict
        else:
            result_msg = f"Resource {resource_type} '{resource_name}' deleted successfully."
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Resource deleted."}],
            "resource_action_result": result_msg,
            "resource_action_status": "success"
        }
    except Exception as e:
        logger.error(f"Delete resource failed: {e}")
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": f"Delete resource failed: {e}"}],
            "resource_action_result": None,
            "resource_action_error": str(e),
            "resource_action_status": "failed"
        }

# --- Tool 4: Prompt for Missing/Invalid Fields ---
"""
This tool prompts the user for missing or invalid fields for resource actions.
It raises an interrupt to stop the agent.
"""
@tool
def prompt_for_missing_action_tool(resource_action_error=None, messages=None, **kwargs):
    """
    Prompts the user for missing or invalid fields for resource actions.
    
    Args:
        resource_action_error (str): The error message.
        messages (list): The list of messages to pass to the LLM.
        **kwargs: Additional keyword arguments.
    """
    msg = resource_action_error or "Missing or invalid fields for resource action."
    updated_messages = list(messages) if messages else []
    updated_messages.append({"role": "system", "content": msg})
    raise interrupt(msg)

class ResourceActionAgent:
    @staticmethod
    def build():
        llm = LLMFactory.get_llm()
        tools = [
            get_resource_tool,
            list_resources_tool,
            delete_resource_tool,
            prompt_for_missing_action_tool,
        ]
        agent = create_react_agent(
            tools=tools,
            model=llm,
            state_schema=ARMAState,
            prompt=RESOURCE_ACTION_SYSTEM_PROMPT,
            name="resource_action_agent"
        )
        return agent
