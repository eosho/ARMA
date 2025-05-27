"""
This agent is responsible for detecting the intent of the user's query and extracting the necessary information.
It also determines the scope of the query and checks for required scope fields.
"""

import logging
from typing import Dict, Any
from langgraph.prebuilt import create_react_agent
from langgraph.types import interrupt
from state import ARMAState
from langchain_community.vectorstores import FAISS
from langchain_openai import AzureOpenAIEmbeddings
from langchain.schema import Document
import os
from dotenv import load_dotenv
from factory.llm_factory import LLMFactory
from prompts import INTENT_EXTRACTION_SYSTEM_PROMPT
import json
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage

# load environment variables
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# --- Tool 1: Intent Extraction ---
"""
This tool extracts intent, resource_type, provided_fields, resource_group_name, subscription_id, subscription_name, and location from the user's prompt using the LLM.
"""
@tool
def extract_intent_tool(messages, **kwargs):
    """
    Extracts intent, resource_type, provided_fields, resource_group_name, subscription_id, subscription_name, and location from the user's prompt using the LLM.
    
    Args:
        messages (list): The list of messages to pass to the LLM.
        **kwargs: Additional keyword arguments.

    Returns:
        dict: The intent, resource_type, provided_fields, resource_group_name, subscription_id, subscription_name, and location.
    """
    llm = LLMFactory.get_llm()
    system_prompt = INTENT_EXTRACTION_SYSTEM_PROMPT
    user_message = messages[-1]["content"] if isinstance(messages[-1], dict) else getattr(messages[-1], "content", "")
    
    # use human message as user message
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message)
    ])
    try:
        result = json.loads(response.content)
    except Exception:
        result = {}
    logger.info(f"LLM intent extraction result: {result}")
    updated_messages = list(messages)
    updated_messages.append({
        "role": "assistant",
        "content": response.content
    })
    return {
        **kwargs,
        "messages": updated_messages,
        "intent": result.get("intent"),
        "resource_type": result.get("resource_type"),
        "provided_fields": result.get("provided_fields", {}),
        "resource_group_name": result.get("resource_group_name"),
        "subscription_id": result.get("subscription_id"),
        "subscription_name": result.get("subscription_name"),
        "location": result.get("location"),
        "user_query": user_message
    }

# --- Tool 2: Template Fetch ---
"""
This tool loads the ARM template from a local file path based on the resource_type.
"""
@tool
def fetch_template_tool(resource_type=None, messages=None, **kwargs):
    """
    Loads the ARM template from a local file path based on the resource_type.
    
    Args:
        resource_type (str): The resource type to fetch the template for.
        messages (list): The list of messages to pass to the LLM.
        **kwargs: Additional keyword arguments.

    Returns:
        dict: The ARM template.
    """
    logger.info(f"Loading template for resource_type: {resource_type}")
    template = {}
    template_path = ""
    template_error = None
    if resource_type:
        try:
            namespace, resource = resource_type.split("/", 1)
            template_path = f"quickstarts/{namespace.lower()}/{resource.lower()}.json"
            logger.info(f"Template path: {template_path}")
            if not os.path.exists(template_path):
                raise FileNotFoundError(f"Template file not found: {template_path}")
            with open(template_path, "r", encoding="utf-8") as f:
                template = json.load(f)
            logger.info(f"Loaded template from {template_path}")
            logger.info(f"Template loaded in fetch_template_tool: {template} (type: {type(template)})")
        except Exception as e:
            logger.exception("template_fetch_tool failed")
            template_error = str(e)
    else:
        template_error = "No resource_type provided."
    updated_messages = list(messages) if messages else []
    updated_messages.append({
        "role": "system",
        "content": f"Template fetch: {template_path or 'not found'}"
    })
    return {
        **kwargs,
        "messages": updated_messages,
        "template": template,
        "template_path": template_path,
        "template_error": template_error
    }

# --- Tool 3: Scope Determination ---
"""
This tool determines the scope from the ARM template schema. Supports subscription and resourceGroups only.
"""
@tool
def determine_scope_tool(template=None, messages=None, **kwargs):
    """
    Determines the scope from the ARM template schema. Supports subscription and resourceGroups only.
    
    Args:
        template (dict): The ARM template.
        messages (list): The list of messages to pass to the LLM.
        **kwargs: Additional keyword arguments.

    Returns:
        dict: The scope.
    """
    scope = None
    try:
        t = template
        if isinstance(t, str):
            t = json.loads(t)
        if t and "$schema" in t:
            schema_url = t["$schema"]
            if "subscription" in schema_url:
                scope = "subscription"
            else:
                scope = "resourceGroup"
    except Exception as e:
        logger.error(f"determine_scope_tool failed: {e}")
    logger.info(f"Determined scope: {scope}")
    updated_messages = list(messages) if messages else []
    updated_messages.append({
        "role": "system",
        "content": f"Scope determined: {scope}"
    })
    return {
        **kwargs,
        "messages": updated_messages,
        "scope": scope
    }

# --- Tool 4: Scope Fields Check ---
"""
This tool checks for required scope fields and interrupts if missing.
"""
@tool
def check_scope_fields_tool(resource_group_name=None, subscription_id=None, subscription_name=None, messages=None, **kwargs):
    """
    Checks for required scope fields and interrupts if missing.
    - resource_group_name must be present
    - Either subscription_id (GUID) or subscription_name (string) must be present
    If missing, interrupts and prompts the user for the missing fields.
    
    Args:
        resource_group_name (str): The resource group name.
        subscription_id (str): The subscription ID.
        subscription_name (str): The subscription name.
        messages (list): The list of messages to pass to the LLM.
        **kwargs: Additional keyword arguments.
    """
    missing = []
    if not resource_group_name:
        missing.append("resource_group_name")
    if not (subscription_id or subscription_name):
        missing.append("subscription_id or subscription_name")
    updated_messages = list(messages) if messages else []
    if missing:
        message = f"Please provide the following required fields: {', '.join(missing)}."
        logger.info(f"Interrupting for missing fields: {missing}")
        updated_messages.append({
            "role": "system",
            "content": message
        })
        return interrupt(message)
    logger.info("All required scope fields are present.")
    updated_messages.append({
        "role": "system",
        "content": "All required scope fields are present."
    })
    return {
        **kwargs,
        "messages": updated_messages,
        "resource_group_name": resource_group_name,
        "subscription_id": subscription_id,
        "subscription_name": subscription_name
    }

class IntentAgent:
    @staticmethod
    def build():
        llm = LLMFactory.get_llm()
        tools = [
            extract_intent_tool,
            check_scope_fields_tool,
            fetch_template_tool,
            determine_scope_tool,
        ]
        agent = create_react_agent(
            tools=tools,
            model=llm,
            prompt=INTENT_EXTRACTION_SYSTEM_PROMPT,
            name="intent_agent",
            state_schema=ARMAState
        )
        return agent