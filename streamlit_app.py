import streamlit as st
import uuid
import asyncio
from langchain_core.messages import AIMessage, HumanMessage
from langchain.schema.runnable.config import RunnableConfig
from utils import get_streamlit_cb
from arma import invoke_arma

APP_ICON = "🤖"
APP_TITLE = f"{APP_ICON} ARMA"

st.title(APP_TITLE)

# Initialize the expander state
if "expander_open" not in st.session_state:
    st.session_state.expander_open = True

with st.expander("Azure Resource Management Assistant (ARMA) via Natural Language", expanded=True):
    st.write("""
    This app demonstrates how to use the StreamlitCallbackHandler to stream the response from the Azure Resource Management Assistant (ARMA).
    The app is built using the LangGraph framework and the Azure Resource Management Assistant (ARMA) is built using the LangGraph framework.
    It consists of 5 agents:
    - **ARMA Supervisor Agent**: Supervises the other agents and orchestrates the overall flow of the application.
    - **Intent Detection Agent**: Detects the intent of the user's request
    - **Template Validation Agent**: Validates the template based on the intent and provided fields
    - **Resource Action Agent**: Can get, list, or delete a resource
    - **Deployment Agent**: Can create or update a resource using an ARM template
    """)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "user_id" not in st.session_state:
    st.session_state.user_id = "user_1"

# Sidebar
with st.sidebar:
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
        st_callback = get_streamlit_cb(st.container())

        # add a thread id to the config
        config = {"configurable": {"thread_id": st.session_state.thread_id, "user_id": st.session_state.user_id}}

        # invoke the graph
        response = invoke_arma().invoke(
            {"messages": [HumanMessage(content=prompt)]},
            config=RunnableConfig(
                **config,
                callbacks=[st_callback]
            )
        )
        
        # get the last message from the response
        last_msg = response["messages"][-1].content
        
        # Add that last message to the st_message_state
        st.session_state.messages.append(AIMessage(content=last_msg))
        
        # visually refresh the complete response after the callback container
        msg_placeholder.write(last_msg)