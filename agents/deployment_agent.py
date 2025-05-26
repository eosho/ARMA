"""
This agent is responsible for deploying the ARM template to Azure.
It can deploy to a resource group or a subscription.
"""

import os
import json
import logging
from typing import Dict, Any
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.resource.resources.models import DeploymentMode
from langgraph.graph import StateGraph, START, END
from state import ARMAState
from datetime import datetime

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger(__name__)

# deployment name
today = datetime.now().strftime("%m-%d-%Y")
deployment_name = f"ai-deployment-{today}"

# --- Helper Functions ---

def ensure_template_dict(template):
    if isinstance(template, str):
        try:
            return json.loads(template)
        except Exception as e:
            logger.error(f"Template string could not be parsed as JSON: {e}")
            raise ValueError("Template is not valid JSON")
    return template

# --- Resource Group Deployment ---
def resource_group_deployment_node(state: Dict[str, Any]) -> Dict[str, Any]:
    state["deployment_status"] = "pending"
    logger.info(f"Resource group deployment started")
    try:
        template = ensure_template_dict(state.get("template"))
    except ValueError as e:
        state["deployment_error"] = str(e)
        state["deployment_status"] = "failed"
        logger.error(f"deployment_error: {state['deployment_error']}")
        return state
    
    parameters = state.get("parameter_file_content", {}).get("parameters", {})
    resource_group = state.get("resource_group_name")
    subscription_id = state.get("subscription_id")
    location = state.get("location", "eastus")  # fallback location
    credential = DefaultAzureCredential()
    client = ResourceManagementClient(credential, subscription_id)
    
    # Check and create resource group if needed
    resource_group_exists = state.get("resource_group_exists", False)
    if not resource_group_exists:
        try:
            client.resource_groups.create_or_update(
                resource_group,
                {"location": location}
            )
            state["resource_group_exists"] = True
            logger.info(f"Created resource group {resource_group} in {location}")
        except Exception as e:
            logger.error(f"Failed to create resource group: {e}")
            state["deployment_error"] = f"Failed to create resource group: {e}"
            state["deployment_status"] = "failed"
            logger.error(f"deployment_error: {state['deployment_error']}")
            return state
    try:
        deployment_poller = client.deployments.begin_create_or_update(
            resource_group,
            deployment_name,
            {
                "properties": {
                    "mode": DeploymentMode.incremental,
                    "template": template,
                    "parameters": parameters
                }
            }
        )
        result = deployment_poller.result()
        state["deployment_result"] = result.as_dict()
        state["deployment_status"] = "succeeded"
        logger.info(f"Deployment to resource group {resource_group} succeeded.")
        logger.info(f"deployment_result: {json.dumps(state['deployment_result'], indent=2)}")
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        state["deployment_error"] = str(e)
        state["deployment_status"] = "failed"
        logger.error(f"deployment_error: {state['deployment_error']}")
    return state

# --- Subscription Deployment ---
def subscription_deployment_node(state: Dict[str, Any]) -> Dict[str, Any]:
    state["deployment_status"] = "pending"
    logger.info(f"Subscription deployment started")
    try:
        template = ensure_template_dict(state.get("template"))
    except ValueError as e:
        state["deployment_error"] = str(e)
        state["deployment_status"] = "failed"
        logger.error(f"deployment_error: {state['deployment_error']}")
        return state
    
    parameters = state.get("parameter_file_content", {}).get("parameters", {})
    subscription_id = state.get("subscription_id")
    location = state.get("location", "eastus")  # required for subscription deployments
    credential = DefaultAzureCredential()
    client = ResourceManagementClient(credential, subscription_id)
    
    try:
        deployment_poller = client.deployments.begin_create_or_update_at_subscription_scope(
            deployment_name,
            {
                "location": location,
                "properties": {
                    "mode": DeploymentMode.incremental,
                    "template": template,
                    "parameters": parameters
                }
            }
        )
        result = deployment_poller.result()
        state["deployment_result"] = result.as_dict()
        state["deployment_status"] = "succeeded"
        logger.info(f"Deployment at subscription scope succeeded.")
        logger.info(f"deployment_result: {json.dumps(state['deployment_result'], indent=2)}")
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        state["deployment_error"] = str(e)
        state["deployment_status"] = "failed"
        logger.error(f"deployment_error: {state['deployment_error']}")
    return state

# --- Graph ---
def build_deployment_graph():
    graph = StateGraph(ARMAState)
    graph.add_node("resource_group_deployment", resource_group_deployment_node)
    graph.add_node("subscription_deployment", subscription_deployment_node)
    # Conditional edge based on scope
    graph.add_conditional_edges(
        START,
        lambda state: "resource_group_deployment" if state.get("scope") == "resourceGroup" else "subscription_deployment",
        {
            "resource_group_deployment": "resource_group_deployment",
            "subscription_deployment": "subscription_deployment"
        }
    )
    graph.add_edge("resource_group_deployment", END)
    graph.add_edge("subscription_deployment", END)
    return graph.compile()