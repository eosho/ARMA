import uuid
from langgraph_supervisor import create_supervisor
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langchain_core.runnables import RunnableConfig
from agents import (
  build_intent_agent,
  build_validation_agent,
  build_resource_action_agent,
  build_deployment_agent
)
from factory.llm_factory import LLMFactory
from prompts import ARMA_SUPERVISOR_PROMPT
from state import ARMAState

# Build agents
intent_agent = build_intent_agent()
template_agent = build_validation_agent()
resource_action_agent = build_resource_action_agent()
deployment_agent = build_deployment_agent()

# Define your LLM (replace with your config)
model = LLMFactory.get_llm()

def invoke_arma():
    # Create the supervisor workflow
    workflow = create_supervisor(
        [intent_agent, template_agent, resource_action_agent, deployment_agent],
        model=model,
        prompt=ARMA_SUPERVISOR_PROMPT,
        supervisor_name="arma_supervisor",
        state_schema=ARMAState,
        output_mode="full_history"
    )

    # compile the workflow
    arma = workflow.compile()
    return arma

# while True:
#     if __name__ == "__main__":
#         graph = invoke_arma()
#         # get user input from command line and exit if "exit"
#         cmd = input("Enter your request (or 'exit' to quit): ")
#         if cmd == "exit":
#             print("Exiting...")
#             break
#         user_input = ({"messages": cmd})
#         print(f"User input: {user_input}")

#     config = RunnableConfig(configurable={"thread_id": 1}, session_id=1, user_id=1)
#     try:
#         messages = graph.invoke(user_input, config=config)
#         for message in messages["messages"]:
#             message.pretty_print()
#     except Exception as e:
#         print(f"Workflow failed: {e}")


# Sample requests:
# create a storage account named eoaiteststorg01 in resource group myrg, subscription e98a7bdd-1e97-452c-939c-4edf569d31f6, location eastus