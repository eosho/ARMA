"""
This agent is responsible for validating the ARM template and parameters against Azure.
It checks if the subscription and resource group exist, validates the parameters against the template,
and prompts the user for missing parameters if any are found.
"""

import json
import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
from langgraph.graph import StateGraph, START, END
from state import ARMAState
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from langgraph.types import interrupt
from factory.llmfactory import get_llm
from prompts.prompts import TEMPLATE_VALIDATION_SYSTEM_PROMPT

# logging
logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Suppress the azure logging
logging.getLogger("azure").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

load_dotenv()

# deployment name
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
deployment_name = f"ai-validation-{timestamp}"

# --- Helper Functions ---

# --- Subscription Check ---
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

# --- Resource Group Check ---
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

# --- Node 1: Subscription Check ---
def check_subscription_node(state: Dict[str, Any]) -> Dict[str, Any]:
    subscription_id = state.get("subscription_id")
    exists = check_subscription_exists(subscription_id) if subscription_id else False
    return {**state, "subscription_exists": exists}

# --- Node 2: Resource Group Check ---
def check_resource_group_node(state: Dict[str, Any]) -> Dict[str, Any]:
    subscription_id = state.get("subscription_id")
    resource_group_name = state.get("resource_group_name")
    exists = (
        check_resource_group_exists(subscription_id, resource_group_name)
        if subscription_id and resource_group_name else False
    )
    return {**state, "resource_group_exists": exists}

# --- Node 3: Template Validation ---
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
        system_prompt = TEMPLATE_VALIDATION_SYSTEM_PROMPT
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

# --- Node 4: Prompt for Missing Parameters ---
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

# --- Node 5: ARM Template Deployment Validation ---
def arm_template_deployment_validation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates the ARM template and parameters against Azure using the Azure SDK (without deploying).
    Stores the validation result and any errors in the state.
    """
    template = state.get("template")
    parameters = state.get("parameter_file_content", {}).get("parameters", {})
    resource_group = state.get("resource_group_name")
    subscription_id = state.get("subscription_id")
    location = state.get("location", "eastus")
    scope = state.get("scope", "resourceGroup")
    credential = DefaultAzureCredential()
    client = ResourceManagementClient(credential, subscription_id)
    try:
        if isinstance(template, str):
            template = json.loads(template)
        if scope == "resourceGroup":
            if not resource_group:
                return {**state, "arm_validation_error": "No resource group specified for validation."}
            poller = client.deployments.begin_validate(
                resource_group,
                deployment_name,
                {
                    "properties": {
                        "mode": "Incremental",
                        "template": template,
                        "parameters": parameters
                    }
                }
            )
        else:
            poller = client.deployments.begin_validate_at_subscription_scope(
                deployment_name,
                {
                    "location": location,
                    "properties": {
                        "mode": "Incremental",
                        "template": template,
                        "parameters": parameters
                    }
                }
            )
        result = poller.result()
        state["validation_result"] = result.as_dict() if hasattr(result, "as_dict") else result
        state["validation_error"] = None
        state["validation_status"] = "success"
        logger.info("ARM template deployment validation succeeded.")
    except Exception as e:
        logger.error(f"ARM template deployment validation failed: {e}")
        state["validation_result"] = None
        state["validation_error"] = str(e)
        state["validation_status"] = "failed"
    return state

# --- Graph ---
def build_template_validation_graph():
    graph = StateGraph(ARMAState)
    graph.add_node("check_subscription", check_subscription_node)
    graph.add_node("check_resource_group", check_resource_group_node)
    graph.add_node("validate", template_validation_node)
    graph.add_node("arm_validate", arm_template_deployment_validation_node)
    graph.add_node("prompt_for_missing", prompt_for_missing_node)

    # Edges
    graph.add_edge(START, "check_subscription")
    graph.add_edge("check_subscription", "check_resource_group")
    graph.add_edge("check_resource_group", "validate")
    # Only run ARM validation if no missing/invalid parameters
    graph.add_conditional_edges(
        "validate",
        lambda state: "prompt_for_missing" if state.get("missing_parameters") or state.get("type_errors") or state.get("validation_error") else "arm_validate",
        {"prompt_for_missing": "prompt_for_missing", "arm_validate": "arm_validate"}
    )
    graph.add_edge("arm_validate", END)
    graph.add_edge("prompt_for_missing", END)
    return graph.compile()