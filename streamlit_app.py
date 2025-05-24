import streamlit as st
import uuid
import asyncio
from langchain_core.messages import AIMessage, HumanMessage
from langchain.schema.runnable.config import RunnableConfig
from st_callable_util import get_streamlit_cb
# from agent_supervisor import invoke_graph
from graph import invoke_graph
import yaml
import json

# Lets load these values from a yaml file with sample yaml
with open("st_config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

APP_TITLE = config["app_title"]
APP_ICON = config["app_icon"]

def format_deployment_summary(res):
    if "deployment_error" in res:
        return f"❌ Deployment failed:\n{res['deployment_error']}"
    if "deployment_result" in res:
        tenant_id = res.get("tenant_id", "fdpo.onmicrosoft.com")
        result = res["deployment_result"]
        summary = [f"✅ Deployment succeeded!"]
        rg = res.get("resource_group_name")
        if rg:
            summary.append(f"\n**Resource Group:** {rg}")
        outputs = result.get("properties", {}).get("outputs")
        portal_link = None
        if outputs:
            summary.append("\n**Outputs:**")
            for k, v in outputs.items():
                summary.append(f"- **{k}**: {v.get('value')}")
                # If the output is a resourceId, add a portal link
                if k.lower().endswith("id") and isinstance(v.get('value'), str) and v.get('value').startswith("/subscriptions/"):
                    portal_link = f"https://ms.portal.azure.com/#@{tenant_id}/resource{v.get('value')}/overview"
        state = result.get("properties", {}).get("provisioningState")
        if state:
            summary.append(f"\n**Provisioning State:** {state}")
        if portal_link:
            summary.append(f"\n[View in Azure Portal]({portal_link})")
        return "\n".join(summary)
    if "validation_error" in res:
        return f"⚠️ Validation error: {res['validation_error']}"
    return "No deployment result available."

st.title(APP_TITLE)
st.markdown("#### StreamlitCallBackHandler Full Implementation")

# Initialize the expander state
if "expander_open" not in st.session_state:
    st.session_state.expander_open = True

with st.expander("Azure Provisioning Agent via Natural Language"):
    st.write("""
    This app demonstrates how to use the StreamlitCallbackHandler to stream the response from the Azure provisioning agent.
    The app is built using the LangGraph framework and the Azure provisioning agent is built using the LangGraph framework.
    It consists of 3 agents:
    - **Intent Detection Agent**: Detects the intent of the user's request
    - **Template Validation Agent**: Validates the template based on the intent and provided fields
    - **Deployment Agent**: Deploys the template to Azure using the Azure ARM template and SDK.
    """)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "user_id" not in st.session_state:
    st.session_state.user_id = "user_1"

# Sidebar
with st.sidebar:
  st.header(f"{APP_ICON} {APP_TITLE}")

  ""
  "Sample app for LangGraph with StreamlitCallbackHandler"
  ""

  if st.button("New Chat", use_container_width=True, icon=":material/chat:"):
      st.session_state.messages = []
      st.session_state.thread_id = str(uuid.uuid4())
      st.session_state.user_id = "user_1"
      st.rerun()

  @st.dialog("Architecture")
  def architecture_dialog() -> None:
      st.image(
          "https://github.com/JoshuaC215/agent-service-toolkit/blob/main/media/agent_architecture.png?raw=true"
      )

  if st.button("Architecture", use_container_width=True, icon=":material/schema:"):
      architecture_dialog()

  with st.popover("Privacy", use_container_width=True, icon=":material/policy:"):
      st.write(
          "Prompts, responses and feedback in this app are not logged."
      )

# Display conversation history on the sidebar in a clean format
with st.sidebar:
    st.header("Conversation History")


# Messages implementation
for msg in st.session_state.messages:
    if type(msg) == AIMessage:
        st.chat_message("assistant").markdown(msg.content)
    if type(msg) == HumanMessage:
        st.chat_message("user").markdown(msg.content)

if prompt := st.chat_input("Enter a message"):
    st.chat_message("user").markdown(prompt)

    with st.chat_message("assistant"):
        msg_placeholder = st.container()
        st_callback = get_streamlit_cb(msg_placeholder)

        # add a thread id to the config
        config = {"configurable": {"thread_id": st.session_state.thread_id, "user_id": st.session_state.user_id}}

        # invoke the graph
        response = invoke_graph(
            {"prompt": prompt},
            config=RunnableConfig(
                **config,
                callbacks=[st_callback]
            )
        )
        
        # Print all agent/system messages to the streamlit app
        for m in response.get('messages', []):
            if isinstance(m, dict):
                st.chat_message(m.get("role", "assistant")).markdown(m.get("content", ""))
            elif hasattr(m, "content"):
                st.chat_message("assistant").markdown(m.content)

        # Print the deployment summary at the end
        summary = format_deployment_summary(response)
        msg_placeholder.markdown(summary)
        st.session_state.messages.append(AIMessage(content=summary))