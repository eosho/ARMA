import logging
import os
import json
from typing import Dict, Any
from datetime import datetime
from langgraph.graph import StateGraph, START, END
from state_schemas import MasterState
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from langgraph.types import interrupt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

def delete_resource_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deletes the specified Azure resource using the Azure SDK.
    """
    subscription_id = state.get("subscription_id")
    resource_group = state.get("resource_group_name")
    resource_type = state.get("resource_type")
    provided_fields = state.get("provided_fields", {})
    resource_name = provided_fields.get("name")
    if not (subscription_id and resource_group and resource_type and resource_name):
        msg = "Missing required fields for delete operation."
        logger.error(msg)
        return interrupt(msg)
    try:
        credential = DefaultAzureCredential()
        client = ResourceManagementClient(credential, subscription_id)
        # resource_type: e.g., Microsoft.Storage/storageAccounts
        namespace, type_name = resource_type.split("/", 1)
        api_version = "2021-04-01"
        logger.info(f"Deleting resource: {resource_type} name={resource_name} rg={resource_group} sub={subscription_id}")
        delete_poller = client.resources.begin_delete(
            resource_group_name=resource_group,
            resource_provider_namespace=namespace,
            parent_resource_path="",
            resource_type=type_name,
            resource_name=resource_name,
            api_version=api_version
        )
        delete_result = delete_poller.result()
        if delete_result is not None:
            # Try to convert to dict if possible
            result_dict = delete_result.as_dict() if hasattr(delete_result, "as_dict") else delete_result
            try:
                result_json = json.dumps(result_dict, indent=2, default=str)
            except Exception:
                result_json = str(result_dict)
            logger.info(f"Delete result: {result_json}")
            state["resource_action_result"] = result_dict
        else:
            msg = f"Resource {resource_type} '{resource_name}' deleted successfully."
            logger.info(msg)
            state["resource_action_result"] = msg
        state["resource_action_status"] = "success"
    except Exception as e:
        logger.error(f"Delete resource failed: {e}")
        state["resource_action_result"] = None
        state["resource_action_error"] = str(e)
        state["resource_action_status"] = "failed"
    return state

def get_resource_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gets details of the specified Azure resource using the Azure SDK.
    """
    subscription_id = state.get("subscription_id")
    resource_group = state.get("resource_group_name")
    resource_type = state.get("resource_type")
    provided_fields = state.get("provided_fields", {})
    resource_name = provided_fields.get("name")
    if not (subscription_id and resource_group and resource_type and resource_name):
        msg = "Missing required fields for get operation."
        logger.error(msg)
        return interrupt(msg)
    try:
        credential = DefaultAzureCredential()
        client = ResourceManagementClient(credential, subscription_id)
        namespace, type_name = resource_type.split("/", 1)
        api_version = "2021-04-01"
        logger.info(f"Getting resource: {resource_type} name={resource_name} rg={resource_group} sub={subscription_id}")
        resource = client.resources.get(
            resource_group_name=resource_group,
            resource_provider_namespace=namespace,
            parent_resource_path="",
            resource_type=type_name,
            resource_name=resource_name,
            api_version=api_version
        )
        resource_dict = resource.as_dict() if hasattr(resource, "as_dict") else resource
        try:
            resource_json = json.dumps(resource_dict, indent=2, default=str)
        except Exception:
            resource_json = str(resource_dict)
        logger.info(f"Resource details: {resource_json}")
        state["resource_action_result"] = resource_dict
        state["resource_action_status"] = "success"
    except Exception as e:
        logger.error(f"Get resource failed: {e}")
        state["resource_action_result"] = None
        state["resource_action_error"] = str(e)
        state["resource_action_status"] = "failed"
    return state

def list_resources_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lists resources of the specified type in the given resource group using the Azure SDK.
    """
    subscription_id = state.get("subscription_id")
    resource_group = state.get("resource_group_name")
    resource_type = state.get("resource_type")
    if not (subscription_id and resource_group and resource_type):
        msg = "Missing required fields for list operation."
        logger.error(msg)
        return interrupt(msg)
    try:
        credential = DefaultAzureCredential()
        client = ResourceManagementClient(credential, subscription_id)
        namespace, type_name = resource_type.split("/", 1)
        api_version = "2021-04-01"
        logger.info(f"Listing resources: {resource_type} in rg={resource_group} sub={subscription_id}")
        resources = client.resources.list_by_resource_group(
            resource_group_name=resource_group,
            filter=f"resourceType eq '{namespace}/{type_name}'"
        )
        resource_list = [r.as_dict() if hasattr(r, "as_dict") else r for r in resources]
        logger.info(f"Resources: {json.dumps(resource_list, indent=2)}")
        state["resource_action_result"] = resource_list
        state["resource_action_status"] = "success"
        logger.info(f"Listed {len(state['resource_action_result'])} resources.")
    except Exception as e:
        logger.error(f"List resources failed: {e}")
        state["resource_action_result"] = None
        state["resource_action_error"] = str(e)
        state["resource_action_status"] = "failed"
    return state

def build_resource_action_graph():
    graph = StateGraph(MasterState)
    graph.add_node("delete_resource", delete_resource_node)
    graph.add_node("get_resource", get_resource_node)
    graph.add_node("list_resources", list_resources_node)
    # Route based on intent
    def route_intent(state):
        intent = state.get("intent")
        if intent == "delete":
            return "delete_resource"
        elif intent == "get":
            return "get_resource"
        elif intent == "list":
            return "list_resources"
        else:
            return END
    graph.add_conditional_edges(START, route_intent, {
        "delete_resource": "delete_resource",
        "get_resource": "get_resource",
        "list_resources": "list_resources",
        END: END
    })
    graph.add_edge("delete_resource", END)
    graph.add_edge("get_resource", END)
    graph.add_edge("list_resources", END)
    return graph 