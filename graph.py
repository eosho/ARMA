"""
This module contains the main graph for the Azure provisioning workflow.
"""

import uuid
import logging
from langgraph.graph import StateGraph, START, END
from agents.intent_detection_langgraph import build_intent_detection_graph
from agents.template_validation_agent import build_template_validation_graph
from state_schemas import MasterState
from agents.deployment_agent import build_deployment_graph
from langchain.storage import InMemoryStore
from langgraph.checkpoint.memory import InMemorySaver

# configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

checkpointer = InMemorySaver()
store = InMemoryStore()

# Compile subgraphs before adding as nodes
graph = StateGraph(MasterState)

# Compile subgraphs
intent_detection_graph = build_intent_detection_graph().compile()
template_validation_graph = build_template_validation_graph().compile()
deployment_graph = build_deployment_graph().compile()

# Add subgraphs as nodes
graph.add_node("intent_detection", intent_detection_graph)
graph.add_node("template_validation", template_validation_graph)
graph.add_node("deployment", deployment_graph)

# Add edges
graph.add_edge(START, "intent_detection")
graph.add_edge("intent_detection", "template_validation")
graph.add_edge("template_validation", "deployment")
graph.add_edge("deployment", END)

compiled_graph = graph.compile(store=store, checkpointer=checkpointer)

def invoke_graph(input_dict, config):
    """
    Invokes the graph with the given input and config.
    Args:
        input_dict (dict): The input to the graph, e.g., {"messages": [...]}
        config (RunnableConfig): The config, including callbacks, etc.
    Returns:
        dict: The response from the graph.
    """
    user_messages = input_dict.get("messages", [])
    return compiled_graph.invoke({"messages": user_messages}, config=config)



thread_config = {"configurable": {"thread_id": str(uuid.uuid4())}}
inputs = [
    # 1st round of conversation,
    {
        "messages": [
            {"role": "user", "content": "create a storage account with the following values, name: eoaiteststorg01, rg: myrg, subscription: e98a7bdd-1e97-452c-939c-4edf569d31f6 and region eastus"}
        ]
    }
]

for idx, user_input in enumerate(inputs):
    print()
    print(f"--- Conversation Turn {idx + 1} ---")
    print()
    print(f"User: {user_input}")
    print()
    result = invoke_graph(
        user_input,
        config=thread_config
    )
    for node_id, value in result.items():
            if isinstance(value, dict) and value.get("messages", []):
                last_message = value["messages"][-1]
                if isinstance(last_message, dict) or last_message.type != "ai":
                    continue
                print(f"{node_id}: {last_message.content}")