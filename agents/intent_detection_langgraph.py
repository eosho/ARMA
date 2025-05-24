import logging
from typing import Dict, Any, TypedDict, Optional
from langgraph.graph import StateGraph, START, END
import re
import json
from langgraph.types import interrupt
from langchain_community.vectorstores import FAISS
from langchain_openai import AzureOpenAIEmbeddings
from langchain.schema import Document
import os
from state_schemas import MasterState
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
from factory.llmfactory import get_llm

# load environment variables
load_dotenv()

# Path to your vector store (default to ./vs_templates)
VECTORSTORE_PATH = os.getenv("TEMPLATE_VECTORSTORE_PATH", "./vs_templates")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# --- Node 1: Intent Extraction ---
def intent_extraction_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Uses the LLM to extract intent, resource_type (full Azure type), provided_fields, resource_group_name, subscription_id, and subscription_name from the prompt.
    The LLM prompt is enhanced to cover edge cases and provide clear instructions and examples.
    """
    llm = get_llm()
    system_prompt = (
        """
        You are an expert Azure cloud assistant. Given a user's request, extract the following as a JSON object:
        - intent: the high-level action (e.g., create, delete, update, get, list, etc.)
        - resource_type: the full Azure resource type (e.g., Microsoft.Storage/storageAccounts, Microsoft.Compute/virtualMachines, Microsoft.KeyVault/vaults, etc.)
        - provided_fields: a JSON object of any parameter values the user provided (if any) (e.g., name, rg, location, tags, sku, etc.)
        - resource_group_name: the resource group name if provided (should be a string, not a GUID)
        - subscription_id: the subscription id if provided (should be a GUID, e.g., 00000000-0000-0000-0000-000000000000)
        - subscription_name: the subscription name if provided (should be a string, not a GUID)
        - location: the location if provided (should be a string, e.g., eastus, westus, etc.). The user could also use region as a synonym.

        Instructions:
        - Treat any of the following as subscription_id: 'subscription id', 'subscription', 'subid', 'sub id'.
        - Treat any of the following as resource_group_name: 'rg', 'resource group', 'resource_group'.
        - If a value is not provided, omit it from the output.
        - If both subscription_id and subscription_name are provided, include both.
        - If the user provides a value that looks like a GUID, treat it as a subscription_id.
        - If the user provides a value that is a string and not a GUID, treat it as a subscription_name.
        - If the user provides fields in any format (e.g., 'name: test', 'resource group: myrg', 'subscription: mysub', 'subscription id: 00000000-0000-0000-0000-000000000000'), extract them appropriately.
        - If the user provides a list of fields, extract all that are relevant.
        - If the user provides no fields, provided_fields should be an empty object.
        - Only return the JSON object, no extra text.
        - Ignore irrelevant or unrelated fields.
        - If a field is ambiguous, make your best guess and include it in provided_fields.

        Examples:

        User request: create a storage account with the following values, name: test, rg: demorg, subscription id: 00000000-0000-0000-0000-000000000000
        Output JSON: {"intent": "create", "resource_type": "Microsoft.Storage/storageAccounts", "provided_fields": {"name": "test", "rg": "demorg", "subscription_id": "00000000-0000-0000-0000-000000000000", "location": "eastus"}, "resource_group_name": "demorg", "subscription_id": "00000000-0000-0000-0000-000000000000"}

        User request: delete a virtual machine named myvm in resource group myrg and subscription mysub
        Output JSON: {"intent": "delete", "resource_type": "Microsoft.Compute/virtualMachines", "provided_fields": {"name": "myvm", "rg": "myrg", "subscription_name": "mysub"}, "resource_group_name": "myrg", "subscription_name": "mysub"}

        User request: update Microsoft.KeyVault/vaults called prodvault in resource group prod-rg, subscription id 11111111-2222-3333-4444-555555555555, location eastus
        Output JSON: {"intent": "update", "resource_type": "Microsoft.KeyVault/vaults", "provided_fields": {"name": "prodvault", "rg": "prod-rg", "subscription_id": "11111111-2222-3333-4444-555555555555", "location": "eastus"}, "resource_group_name": "prod-rg", "subscription_id": "11111111-2222-3333-4444-555555555555"}

        User request: list all SQL servers in resource group sqlrg
        Output JSON: {"intent": "list", "resource_type": "Microsoft.Sql/servers", "provided_fields": {"rg": "sqlrg"}, "resource_group_name": "sqlrg"}

        User request: get details for cosmosdb account cosmos1 in subid 22222222-3333-4444-5555-666666666666
        Output JSON: {"intent": "get", "resource_type": "Microsoft.DocumentDB/databaseAccounts", "provided_fields": {"name": "cosmos1", "subscription_id": "22222222-3333-4444-5555-666666666666"}, "subscription_id": "22222222-3333-4444-5555-666666666666"}

        User request: create an app service plan called myplan in resource group webapps, subscription my-subscription, location westus2, sku S1
        Output JSON: {"intent": "create", "resource_type": "Microsoft.Web/serverfarms", "provided_fields": {"name": "myplan", "rg": "webapps", "subscription_name": "my-subscription", "location": "westus2", "sku": "S1"}, "resource_group_name": "webapps", "subscription_name": "my-subscription"}

        User request: delete storage account mystorage
        Output JSON: {"intent": "delete", "resource_type": "Microsoft.Storage/storageAccounts", "provided_fields": {"name": "mystorage"}}

        User request: create a key vault named kv1
        Output JSON: {"intent": "create", "resource_type": "Microsoft.KeyVault/vaults", "provided_fields": {"name": "kv1"}}

        User request: remove resource group demorg
        Output JSON: {"intent": "delete", "resource_type": "Microsoft.Resources/resourceGroups", "provided_fields": {"name": "demorg"}, "resource_group_name": "demorg"}

        User request: create a virtual machine with name: vm1, rg: test-rg, sub id: mysub, tags: {"env": "dev"}
        Output JSON: {"intent": "create", "resource_type": "Microsoft.Compute/virtualMachines", "provided_fields": {"name": "vm1", "rg": "test-rg", "subscription_name": "mysub", "tags": {"env": "dev"}}, "resource_group_name": "test-rg", "subscription_name": "mysub"}

        User request: create a storage account
        Output JSON: {"intent": "create", "resource_type": "Microsoft.Storage/storageAccounts", "provided_fields": {}}

        User request: list all resources
        Output JSON: {"intent": "list", "provided_fields": {}}

        User request: create a SQL server with name: sql1, resource group: db-rg, subscription: 33333333-4444-5555-6666-777777777777, location: eastus2
        Output JSON: {"intent": "create", "resource_type": "Microsoft.Sql/servers", "provided_fields": {"name": "sql1", "rg": "db-rg", "subscription_id": "33333333-4444-5555-6666-777777777777", "location": "eastus2"}, "resource_group_name": "db-rg", "subscription_id": "33333333-4444-5555-6666-777777777777"}

        User request: delete cosmosdb account cosmos2 in resource group cosmos-rg
        Output JSON: {"intent": "delete", "resource_type": "Microsoft.DocumentDB/databaseAccounts", "provided_fields": {"name": "cosmos2", "rg": "cosmos-rg"}, "resource_group_name": "cosmos-rg"}

        User request: create a storage account with name: teststorage, resource group: test-rg, subscription: test-subscription, location: eastus, tags: {"env": "test", "owner": "alice"}
        Output JSON: {"intent": "create", "resource_type": "Microsoft.Storage/storageAccounts", "provided_fields": {"name": "teststorage", "rg": "test-rg", "subscription_name": "test-subscription", "location": "eastus", "tags": {"env": "test", "owner": "alice"}}, "resource_group_name": "test-rg", "subscription_name": "test-subscription"}

        User request: {user_prompt}
        Output JSON:
        """
    )
    user_message = state['messages'][-1].content
    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ])
    try:
        result = json.loads(response.content)
    except Exception:
        result = {}
    logger.info(f"LLM intent extraction result: {result}")
    return {
        **state,
        "intent": result.get("intent"),
        "resource_type": result.get("resource_type"),
        "provided_fields": result.get("provided_fields", {}),
        "resource_group_name": result.get("resource_group_name"),
        "subscription_id": result.get("subscription_id"),
        "subscription_name": result.get("subscription_name"),
        "location": result.get("location"),
        "user_query": state["messages"][-1].content
    }

# --- Node 2: Template Fetch ---
def template_fetch_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dynamically loads the ARM template from a local file path based on the resource_type.
    E.g., Microsoft.Storage/storageAccounts -> quickstarts/microsoft.storage/storageaccounts.json
    """
    resource_type = state.get("resource_type")
    logger.info(f"Loading template for resource_type: {resource_type}")
    try:
        if not resource_type:
            raise ValueError("No resource_type provided.")
        namespace, resource = resource_type.split("/", 1)
        template_path = f"quickstarts/{namespace.lower()}/{resource.lower()}.json"
        logger.info(f"Template path: {template_path}")
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template file not found: {template_path}")
        with open(template_path, "r", encoding="utf-8") as f:
            template_json = f.read()
        logger.info(f"Loaded template from {template_path}")
        logger.info(f"Template: {template_json}")
        return {**state, "template": template_json, "template_path": template_path}
    except Exception as e:
        logger.exception("template_fetch_node failed")
        return {**state, "template": "{}", "template_path": "", "template_error": str(e)}

# --- Node 3: Scope Determination ---
def scope_determination_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Determines the scope from the ARM template schema.
    """
    template = state.get("template")
    scope = None
    try:
        if isinstance(template, str):
            template = json.loads(template)
        if template and "$schema" in template:
            schema_url = template["$schema"]
            if "subscription" in schema_url:
                scope = "subscription"
            elif "managementGroup" in schema_url:
                scope = "managementGroup"
            elif "tenant" in schema_url:
                scope = "tenant"
            else:
                scope = "resourceGroup"
    except Exception as e:
        logger.error(f"scope_determination_node failed: {e}")
    logger.info(f"Determined scope: {scope}")
    return {**state, "scope": scope}

# --- Node 4: Scope Fields Check ---
def scope_fields_check_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Checks for required scope fields and interrupts if missing.
    - resource_group_name must be present
    - Either subscription_id (GUID) or subscription_name (string) must be present
    If missing, interrupts and prompts the user for the missing fields.
    """
    missing = []
    if not state.get("resource_group_name"):
        missing.append("resource_group_name")
    if not (state.get("subscription_id") or state.get("subscription_name")):
        missing.append("subscription_id or subscription_name")
    if missing:
        message = f"Please provide the following required fields: {', '.join(missing)}."
        logger.info(f"Interrupting for missing fields: {missing}")
        return interrupt(message)
    logger.info("All required scope fields are present.")
    return state

# --- Graph Construction ---
def build_intent_detection_graph():
    graph = StateGraph(MasterState)
    graph.add_node("intent_extraction", intent_extraction_node)
    graph.add_node("scope_fields_check", scope_fields_check_node)
    graph.add_node("template_fetch", template_fetch_node)
    graph.add_node("scope_determination", scope_determination_node)
    # Edges
    graph.add_edge(START, "intent_extraction")
    graph.add_edge("intent_extraction", "scope_fields_check")
    graph.add_edge("scope_fields_check", "template_fetch")
    graph.add_edge("template_fetch", "scope_determination")
    graph.add_edge("scope_determination", END)
    return graph

# if __name__ == "__main__":
#     import argparse
#     parser = argparse.ArgumentParser(description="Run the intent detection and template fetch workflow.")
#     parser.add_argument("--prompt", type=str, help="User prompt/question", required=True)
#     args = parser.parse_args()
#     state = {"prompt": args.prompt}
#     graph = build_intent_detection_graph().compile()
#     try:
#         result = graph.invoke(state)
#         logger.info("Intent detection workflow completed successfully.")
#         print("\n--- Final State ---\n")
#         for k, v in result.items():
#             print(f"{k}: {v}")
#     except Exception as e:
#         logger.error(f"Intent detection workflow failed: {e}")