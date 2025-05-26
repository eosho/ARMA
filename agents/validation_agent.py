"""
This agent is responsible for validating the ARM template and parameters against Azure.
It checks if the subscription and resource group exist, validates the parameters against the template,
and prompts the user for missing parameters if any are found.
"""

import json
import logging
from datetime import datetime
from langgraph.prebuilt import create_react_agent
from state import ARMAState
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from langgraph.types import interrupt
from factory.llm_factory import LLMFactory
from prompts import VALIDATION_SYSTEM_PROMPT
from langchain_core.tools import tool

# logging
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

load_dotenv()

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
deployment_name = f"ai-validation-{timestamp}"

# --- Tool 1: Subscription Check ---
"""
This tool checks if the subscription exists and is enabled.
It now supports lookup by either subscription_id or subscription_name, and always returns both in the state.
"""
@tool
def check_subscription_tool(subscription_id=None, subscription_name=None, messages=None, **kwargs):
    """
    Checks if the subscription exists and is enabled. Accepts either subscription_id or subscription_name.
    If only one is provided, looks up the other. Always returns both in the state.
    
    Args:
        subscription_id (str): The subscription ID.
        subscription_name (str): The subscription name.
        messages (list): The list of messages to pass to the LLM.
    """
    exists = False
    found_id = subscription_id
    found_name = subscription_name
    mismatch = False
    try:
        credential = DefaultAzureCredential()
        sub_client = SubscriptionClient(credential)
        for sub in sub_client.subscriptions.list():
            # Normalize for comparison
            sub_id = sub.subscription_id
            sub_name = (sub.display_name or '').strip().lower()
            if subscription_id and sub_id == subscription_id:
                found_name = sub.display_name
                if subscription_name and sub_name != subscription_name.strip().lower():
                    mismatch = True
                if sub.state.lower() == "enabled":
                    exists = True
                break
            elif subscription_name and sub_name == subscription_name.strip().lower():
                found_id = sub.subscription_id
                if subscription_id and sub_id != subscription_id:
                    mismatch = True
                if sub.state.lower() == "enabled":
                    exists = True
                break
    except Exception as e:
        logger.error(f"Failed to check subscription: {e}")
    updated_messages = list(messages) if messages else []
    if mismatch:
        updated_messages.append({
            "role": "system",
            "content": f"Warning: Provided subscription_id and subscription_name do not match. Using values from Azure."
        })
    updated_messages.append({
        "role": "system",
        "content": f"Subscription check: {'exists' if exists else 'not found or not enabled'} (ID: {found_id}, Name: {found_name})"
    })
    return {
        **kwargs,
        "messages": updated_messages,
        "subscription_exists": exists,
        "subscription_id": found_id,
        "subscription_name": found_name
    }

# --- Tool 2: Resource Group Check ---
"""
This tool checks if the resource group exists in the given subscription.
"""
@tool
def check_resource_group_tool(resource_group_name=None, subscription_id=None, messages=None, **kwargs):
    """
    Checks if the resource group exists in the given subscription.
    
    Args:
        resource_group_name (str): The resource group name.
        subscription_id (str): The subscription ID.
    """
    exists = False
    try:
        if subscription_id and resource_group_name:
            credential = DefaultAzureCredential()
            rg_client = ResourceManagementClient(credential, subscription_id)
            exists = rg_client.resource_groups.check_existence(resource_group_name)
    except Exception as e:
        logger.error(f"Failed to check resource group: {e}")
    updated_messages = list(messages) if messages else []
    updated_messages.append({
        "role": "system",
        "content": f"Resource group check: {'exists' if exists else 'not found'}"
    })
    return {
        **kwargs,
        "messages": updated_messages,
        "resource_group_exists": exists
    }

# --- Tool 3: Create Resource Group ---
"""
This tool creates a resource group in the given subscription.
"""
@tool
def create_resource_group_tool(resource_group_name=None, subscription_id=None, location=None, messages=None, **kwargs):
    """
    Creates a resource group in the given subscription.
    
    Args:
        resource_group_name (str): The resource group name.
        subscription_id (str): The subscription ID.
        location (str): The location.
    """
    if not (resource_group_name and subscription_id and location):
        logger.error("Missing required fields for resource group creation.")
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Missing required fields for resource group creation."}],
            "resource_group_creation_status": "failed",
            "resource_group_creation_error": "Missing required fields for resource group creation."
        }
    try:
        credential = DefaultAzureCredential()
        rg_client = ResourceManagementClient(credential, subscription_id)
        rg_client.resource_groups.create_or_update(
            resource_group_name,
            {
                "location": location
            }
        )
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": "Resource group created successfully."}],
            "resource_group_creation_status": "success"
        }
    except Exception as e:
        logger.error(f"Failed to create resource group: {e}")
        return {
            **kwargs,
            "messages": (messages or []) + [{"role": "system", "content": f"Failed to create resource group: {e}"}],
            "resource_group_creation_status": "failed",
            "resource_group_creation_error": str(e)
        }

# --- Tool 4: Template Validation ---
"""
This tool validates the provided fields against the template parameters using the LLM.
"""
@tool
def template_validation_tool(template=None, provided_fields=None, messages=None, **kwargs):
    """
    Validates the provided fields against the template parameters using the LLM.
    
    Args:
        template (dict): The ARM template.
        provided_fields (dict): The provided fields.
        messages (list): The list of messages to pass to the LLM.
    """
    if not template:
        logger.error("No template found in state for validation.")
        validation_error = "No template found."
        parameter_file_content = {}
        missing_parameters = []
        extra_fields = []
    else:
        try:
            t = template
            if isinstance(t, str):
                t = json.loads(t)
            parameters = t.get("parameters", {})
            if not parameters:
                logger.warning("No parameters section found in template.")
                validation_error = "No parameters section in template."
                parameter_file_content = {}
                missing_parameters = []
                extra_fields = []
            else:
                llm = LLMFactory.get_llm()
                system_prompt = VALIDATION_SYSTEM_PROMPT
                response = llm.invoke([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Template parameters:\n{json.dumps({'parameters': parameters}, indent=2)}"},
                    {"role": "user", "content": f"Provided fields:\n{json.dumps(provided_fields or {}, indent=2)}"},
                    {"role": "user", "content": "Validate the provided fields against the template parameters and return the result as described."}
                ])
                try:
                    content = response.content.strip()
                    if content.startswith('```'):
                        lines = content.split('\n')
                        lines = lines[1:]
                        if lines and lines[-1].strip().startswith('```'):
                            lines = lines[:-1]
                        content = '\n'.join(lines).strip()
                    result = json.loads(content)
                except Exception:
                    logger.error(f"Failed to parse LLM output: {response.content}")
                    result = {"parameter_file_content": {}, "missing_parameters": [], "extra_fields": [], "validation_error": "Failed to parse LLM output."}
                logger.info(f"LLM template validation result: {result}")
                parameter_file_content = result.get("parameter_file_content", {})
                missing_parameters = result.get("missing_parameters", [])
                extra_fields = result.get("extra_fields", [])
                validation_error = result.get("validation_error")
        except Exception as e:
            logger.error(f"Template validation failed: {e}")
            parameter_file_content = {}
            missing_parameters = []
            extra_fields = []
            validation_error = str(e)
    updated_messages = list(messages) if messages else []
    updated_messages.append({
        "role": "system",
        "content": "Template validation completed."
    })
    # DO NOT overwrite template in the return!
    return {
        **kwargs,
        "messages": updated_messages,
        "parameter_file_content": parameter_file_content,
        "missing_parameters": missing_parameters,
        "extra_fields": extra_fields,
        "validation_error": validation_error
    }

# --- Tool 4: Prompt for Missing Parameters ---
"""
This tool prompts the user for missing or invalid parameters.
"""
@tool
def prompt_for_missing_tool(missing_parameters=None, validation_error=None, messages=None, **kwargs):
    """
    Prompts the user for missing or invalid parameters.
    
    Args:
        missing_parameters (list): The list of missing parameters.
        validation_error (str): The validation error.
    """
    messages_list = []
    if missing_parameters:
        messages_list.append(f"Missing required parameters: {', '.join(missing_parameters)}.")
    if validation_error:
        messages_list.append(f"Validation error: {validation_error}")
    if not messages_list:
        messages_list.append("No missing or invalid parameters detected.")
    user_prompt_message = " ".join(messages_list)
    logger.info(f"Interrupting for user input: {user_prompt_message}")
    updated_messages = list(messages) if messages else []
    updated_messages.append({
        "role": "system",
        "content": user_prompt_message
    })
    raise interrupt(user_prompt_message)

# --- Tool 5a: ARM Template Deployment Validation (Resource Group Scope) ---
"""
This tool validates the ARM template and parameters against Azure at the resource group scope (without deploying).
"""
@tool
def arm_validation_resource_group_tool(template=None, parameter_file_content=None, resource_group_name=None, subscription_id=None, location=None, scope=None, messages=None, **kwargs):
    """
    Validates the ARM template and parameters against Azure at the resource group scope (without deploying).
    Stores the validation result and any errors in the state.
    
    Args:
        template (dict): The ARM template.
        parameter_file_content (dict): The parameter file content.
        resource_group_name (str): The resource group name.
        subscription_id (str): The subscription ID.
        location (str): The location.
        scope (str): The scope.
        messages (list): The list of messages to pass to the LLM.
        **kwargs: Additional keyword arguments.
    """
    logger.info(f"[arm_validation_resource_group_tool] Template: {template}")
    credential = DefaultAzureCredential()
    validation_result = None
    validation_error = None
    validation_status = None
    try:
        t = template
        if isinstance(t, str):
            t = json.loads(t)
        if not t.get('$schema'):
            raise ValueError("Template missing $schema property")
        parameters = (parameter_file_content or {}).get("parameters", {})
        client = ResourceManagementClient(credential, subscription_id)
        if not resource_group_name:
            validation_error = "No resource group specified for validation."
        else:
            poller = client.deployments.begin_validate(
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
            validation_result = result.as_dict() if hasattr(result, "as_dict") else result
            validation_error = None
            validation_status = "success"
        logger.info("ARM template deployment validation (resource group) succeeded.")
    except Exception as e:
        logger.error(f"ARM template deployment validation (resource group) failed: {e}")
        validation_result = None
        validation_error = str(e)
        validation_status = "failed"
    updated_messages = list(messages) if messages else []
    updated_messages.append({
        "role": "system",
        "content": "ARM template deployment validation (resource group) completed."
    })
    return {
        **kwargs,
        "messages": updated_messages,
        "validation_result": validation_result,
        "validation_error": validation_error,
        "validation_status": validation_status
    }

# --- Tool 5b: ARM Template Deployment Validation (Subscription Scope) ---
"""
This tool validates the ARM template and parameters against Azure at the subscription scope (without deploying).
"""
@tool
def arm_validation_subsciption_tool(template=None, parameter_file_content=None, subscription_id=None, location=None, scope=None, messages=None, **kwargs):
    """
    Validates the ARM template and parameters against Azure at the subscription scope (without deploying).
    Stores the validation result and any errors in the state.
    
    Args:
        template (dict): The ARM template.
        parameter_file_content (dict): The parameter file content.
        subscription_id (str): The subscription ID.
        location (str): The location.
        scope (str): The scope.
        messages (list): The list of messages to pass to the LLM.
        **kwargs: Additional keyword arguments.
    """
    logger.info(f"[arm_validation_subsciption_tool] Template: {template}")
    credential = DefaultAzureCredential()
    validation_result = None
    validation_error = None
    validation_status = None
    try:
        t = template
        if isinstance(t, str):
            t = json.loads(t)
        if not t.get('$schema'):
            raise ValueError("Template missing $schema property")
        parameters = (parameter_file_content or {}).get("parameters", {})
        client = ResourceManagementClient(credential, subscription_id)
        poller = client.deployments.begin_validate_at_subscription_scope(
            deployment_name,
            {
                "location": location or "eastus",
                "properties": {
                    "mode": "Incremental",
                    "template": t,
                    "parameters": parameters
                }
            }
        )
        result = poller.result()
        validation_result = result.as_dict() if hasattr(result, "as_dict") else result
        validation_error = None
        validation_status = "success"
        logger.info("ARM template deployment validation (subscription) succeeded.")
    except Exception as e:
        logger.error(f"ARM template deployment validation (subscription) failed: {e}")
        validation_result = None
        validation_error = str(e)
        validation_status = "failed"
    updated_messages = list(messages) if messages else []
    updated_messages.append({
        "role": "system",
        "content": "ARM template deployment validation (subscription) completed."
    })
    return {
        **kwargs,
        "messages": updated_messages,
        "validation_result": validation_result,
        "validation_error": validation_error,
        "validation_status": validation_status
    }

# --- Build ReAct Agent ---
"""
This function builds the ReAct agent for template validation.
It uses the tools defined above.
"""
def build_validation_agent():
    llm = LLMFactory.get_llm()
    tools = [
        check_subscription_tool,
        check_resource_group_tool,
        create_resource_group_tool,
        template_validation_tool,
        prompt_for_missing_tool,
        arm_validation_resource_group_tool,
        arm_validation_subsciption_tool,
    ]
    agent = create_react_agent(
        tools=tools,
        model=llm,
        state_schema=ARMAState,
        prompt=VALIDATION_SYSTEM_PROMPT,
        name="validation_agent"
    )
    return agent