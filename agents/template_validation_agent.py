import json
import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
from langgraph.graph import StateGraph, START, END
from state_schemas import MasterState
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from langgraph.types import interrupt
from factory.llmfactory import get_llm
logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Suppress the azure logging
logging.getLogger("azure").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

load_dotenv()

def check_subscription_exists(subscription_id: str) -> bool:
    """
    Returns True if the subscription exists and is enabled, False otherwise.
    """
    try:
        credential = DefaultAzureCredential()
        sub_client = SubscriptionClient(credential)
        for sub in sub_client.subscriptions.list():
            if sub.subscription_id == subscription_id and sub.state.lower() == "enabled":
                logger.info(f"Subscription {subscription_id} exists and is enabled.")
                return True
        return False
    except Exception as e:
        logger.error(f"Failed to check subscription: {e}")
        return False

def check_resource_group_exists(subscription_id: str, resource_group_name: str) -> bool:
    """
    Returns True if the resource group exists in the given subscription, False otherwise.
    """
    try:
        credential = DefaultAzureCredential()
        rg_client = ResourceManagementClient(credential, subscription_id)
        rg_exists = rg_client.resource_groups.check_existence(resource_group_name)
        if rg_exists:
            logger.info(f"Resource group {resource_group_name} exists in subscription {subscription_id}.")
        return rg_exists
    except Exception as e:
        logger.error(f"Failed to check resource group: {e}")
        return False

def check_subscription_node(state: Dict[str, Any]) -> Dict[str, Any]:
    subscription_id = state.get("subscription_id")
    exists = check_subscription_exists(subscription_id) if subscription_id else False
    return {**state, "subscription_exists": exists}

def check_resource_group_node(state: Dict[str, Any]) -> Dict[str, Any]:
    subscription_id = state.get("subscription_id")
    resource_group_name = state.get("resource_group_name")
    exists = (
        check_resource_group_exists(subscription_id, resource_group_name)
        if subscription_id and resource_group_name else False
    )
    return {**state, "resource_group_exists": exists}

def _is_type_valid(value, expected_type: str) -> bool:
    """Validate value against ARM template type."""
    type_map = {
        "string": str,
        "int": int,
        "bool": bool,
        "array": list,
        "object": dict,
        "securestring": str,
        "secureObject": dict,
        # Add more ARM types as needed
    }
    py_type = type_map.get(expected_type.lower())
    if py_type is None:
        return True  # Unknown type, skip validation
    if expected_type.lower() == "int":
        try:
            int(value)
            return True
        except Exception:
            return False
    return isinstance(value, py_type)

def template_validation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    template = state.get("template")
    provided_fields = state.get("provided_fields", {})
    if not template:
        logger.error("No template found in state for validation.")
        return {**state, "validation_error": "No template found."}
    try:
        if isinstance(template, str):
            template = json.loads(template)
        parameters = template.get("parameters", {})
        if not parameters:
            logger.warning("No parameters section found in template.")
            return {**state, "validation_error": "No parameters section in template."}

        llm = get_llm()
        system_prompt = """
You are an Azure ARM template parameter validator.

Given:
- The ARM template parameters (as JSON)
- The provided_fields (as JSON)

Instructions:
- For each parameter in the template, check if a value is provided in provided_fields (exact key match).
- You should be able to intelligently map provided_fields key/value pairs to parameter names and parameter value types. E.g. "name" would match "storageAccountName", "vmName", "dbName" etc.
- If a required parameter is missing, add it to "missing_parameters".
- If a provided_fields key does not match any parameter, add it to "extra_fields".
- If a provided value is of the wrong type or not in allowed values, add a message to "validation_error".
- If all required parameters are present and valid, return a "parameter_file_content" JSON object mapping parameter names to their values (in the format {"parameters": {name: {"value": value}}}).
- Only return the JSON object, no extra text.

Examples:

Template parameters:
{"parameters": {"name": {"type": "string"}, "location": {"type": "string", "allowedValues": ["eastus", "westus"]}, "sku": {"type": "string", "defaultValue": "Standard"}}}
Provided fields:
{"name": "testsa", "location": "eastus"}
Output:
{"parameter_file_content": {"parameters": {"name": {"value": "testsa"}, "location": {"value": "eastus"}}}, "missing_parameters": [], "extra_fields": [], "validation_error": null}

Template parameters:
{"parameters": {"name": {"type": "string"}, "location": {"type": "string", "allowedValues": ["eastus", "westus"]}, "sku": {"type": "string", "defaultValue": "Standard"}}}
Provided fields:
{"location": "centralus"}
Output:
{"parameter_file_content": {}, "missing_parameters": ["name"], "extra_fields": [], "validation_error": "location value 'centralus' is not allowed. Allowed values: ['eastus', 'westus']"}

Template parameters:
{"parameters": {"name": {"type": "string"}, "count": {"type": "int"}}}
Provided fields:
{"name": "vm1", "count": "notanint", "foo": "bar"}
Output:
{"parameter_file_content": {}, "missing_parameters": [], "extra_fields": ["foo"], "validation_error": "count value 'notanint' is not a valid int."}
"""
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Template parameters:\n{json.dumps({'parameters': parameters}, indent=2)}"},
            {"role": "user", "content": f"Provided fields:\n{json.dumps(provided_fields, indent=2)}"},
            {"role": "user", "content": "Validate the provided fields against the template parameters and return the result as described."}
        ])
        try:
            content = response.content.strip()
            # Remove markdown code block if present
            if content.startswith('```'):
                lines = content.split('\n')
                # Remove the first line (``` or ```json)
                lines = lines[1:]
                # Remove the last line if it's ```
                if lines and lines[-1].strip().startswith('```'):
                    lines = lines[:-1]
                content = '\n'.join(lines).strip()
            result = json.loads(content)
        except Exception:
            logger.error(f"Failed to parse LLM output: {response.content}")
            result = {"parameter_file_content": {}, "missing_parameters": [], "extra_fields": [], "validation_error": "Failed to parse LLM output."}
        logger.info(f"LLM template validation result: {result}")
        return {
            **state,
            "parameter_file_content": result.get("parameter_file_content", {}),
            "missing_parameters": result.get("missing_parameters", []),
            "extra_fields": result.get("extra_fields", []),
            "validation_error": result.get("validation_error"),
        }
    except Exception as e:
        logger.error(f"Template validation failed: {e}")
        return {**state, "validation_error": str(e)}

def prompt_for_missing_node(state: Dict[str, Any]) -> Dict[str, Any]:
    from langgraph.types import interrupt
    missing = state.get("missing_parameters", [])
    validation_error = state.get("validation_error")

    messages = []
    if missing:
        messages.append(f"Missing required parameters: {', '.join(missing)}.")
    if validation_error:
        messages.append(f"Validation error: {validation_error}")

    if not messages:
        messages.append("No missing or invalid parameters detected.")

    user_prompt_message = " ".join(messages)
    logger.info(f"Interrupting for user input: {user_prompt_message}")
    return interrupt(user_prompt_message)

def build_template_validation_graph():
    graph = StateGraph(MasterState)
    graph.add_node("check_subscription", check_subscription_node)
    graph.add_node("check_resource_group", check_resource_group_node)
    graph.add_node("validate", template_validation_node)
    graph.add_node("prompt_for_missing", prompt_for_missing_node)

    # Edges
    graph.add_edge(START, "check_subscription")
    graph.add_edge("check_subscription", "check_resource_group")
    graph.add_edge("check_resource_group", "validate")
    graph.add_conditional_edges(
        "validate",
        lambda state: "prompt_for_missing" if state.get("missing_parameters") or state.get("type_errors") else END,
        {"prompt_for_missing": "prompt_for_missing", END: END}
    )
    graph.add_edge("prompt_for_missing", END)
    return graph