import json
import logging
import os
import sys
import chainlit as cl
import uuid
from langchain.schema.runnable.config import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage
from graph import invoke_graph
from agents.intent_detection_langgraph import build_intent_detection_graph
from agents.deployment_agent import build_deployment_graph
from agents.template_validation_agent import build_template_validation_graph

# Configure a logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def format_deployment_summary(res):
    if "deployment_error" in res:
        return f"❌ Deployment failed:\n{res['deployment_error']}"
    if "deployment_result" in res:
        result = res["deployment_result"]
        summary = ["✅ Deployment succeeded!"]
        # Add resource group or scope info if available
        rg = res.get("resource_group_name")
        if rg:
            summary.append(f"Resource Group: {rg}")
        # Add outputs if available
        outputs = result.get("properties", {}).get("outputs")
        portal_link = None
        if outputs:
            summary.append("Outputs:")
            for k, v in outputs.items():
                summary.append(f"  - {k}: {v.get('value')}")
                # If the output is a resourceId, add a portal link
                if k.lower().endswith("id") and isinstance(v.get('value'), str) and v.get('value').startswith("/subscriptions/"):
                    portal_link = f"https://ms.portal.azure.com/#@/resource{v.get('value')}/overview"
        # Add provisioning state if available
        state = result.get("properties", {}).get("provisioningState")
        if state:
            summary.append(f"Provisioning State: {state}")
        if portal_link:
            summary.append(f"[View in Azure Portal]({portal_link})")
        return "\n".join(summary)
    if "validation_error" in res:
        return f"⚠️ Validation error: {res['validation_error']}"
    return "No deployment result available."

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Provision a storage account",
            message="create a storage account with the following values, name: eoaiteststorg01, rg: myrg, subscription: e98a7bdd-1e97-452c-939c-4edf569d31f6 and region eastus"
            ),

        cl.Starter(
            label="Provision a key vault",
            message="create a key vault with the following values, key vault name: eoaitestkv01, rg: myrg, subscription: e98a7bdd-1e97-452c-939c-4edf569d31f6 and region eastus"
            )
    ]

@cl.on_chat_start
async def on_chat_start():
    print("A new chat session has started!")

@cl.on_message
async def on_message(msg: cl.Message):
    config = {"configurable": {"thread_id": uuid.uuid4()}}

    inputs = {"prompt": msg.content}
    cb = cl.AsyncLangchainCallbackHandler(
        stream_final_answer=True
    )
    cb._schema_format = "original+chat"
    # res = invoke_graph(
    #     inputs,
    #     config=RunnableConfig(
    #         **config,
    #         callbacks=[cb]
    #         ),
    #     )
    intent_detection_graph = build_intent_detection_graph()
    intent_result = intent_detection_graph.invoke(inputs, config=RunnableConfig(
        **config,
        callbacks=[cb]
    ))
    
    validation_graph = build_template_validation_graph()
    validation_result = validation_graph.invoke(intent_result, config=RunnableConfig(
        **config,
        callbacks=[cb]
    ))

    deployment_graph = build_deployment_graph()
    deployment_result = deployment_graph.invoke(validation_result, config=RunnableConfig(
        **config,
        callbacks=[cb]
    ))
    
    # add all the messages to the state
    state = {
        "messages": [
            {"role": "user", "content": msg.content},
            {"role": "assistant", "content": intent_result},
            {"role": "assistant", "content": validation_result},
            {"role": "assistant", "content": deployment_result}
        ]
    }
    final_message = format_deployment_summary(deployment_result)
    await cl.Message(content=state).send()
