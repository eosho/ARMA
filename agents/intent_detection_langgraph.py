"""
This agent is responsible for detecting the intent of the user's query and extracting the necessary information.
It also determines the scope of the query and checks for required scope fields.
"""

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
from state import MasterState
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
from factory.llmfactory import get_llm
from prompts.prompts import INTENT_EXTRACTION_SYSTEM_PROMPT

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
    The LLM prompt is loaded from prompts.prompts.INTENT_EXTRACTION_SYSTEM_PROMPT for maintainability.
    """
    llm = get_llm()
    system_prompt = INTENT_EXTRACTION_SYSTEM_PROMPT
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
    Determines the scope from the ARM template schema. Supports subscription and resourceGroups only.
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
    graph.add_conditional_edges(
        "scope_fields_check",
        lambda state: "template_fetch" if state.get("intent") in ["create", "update"] else END
    )
    graph.add_edge("template_fetch", "scope_determination")
    graph.add_edge("scope_determination", END)
    return graph.compile()

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