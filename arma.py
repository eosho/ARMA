"""
This file contains the ARMA workflow and the agents that make up the ARMA workflow, now wrapped in a class for extensibility and clarity.
"""

import uuid
import logging
from typing import List, Optional, Any
from langgraph_supervisor import create_supervisor
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langchain_core.runnables import RunnableConfig
from agents import (
  IntentAgent,
  ValidationAgent,
  ResourceActionAgent,
  DeploymentAgent
)
from factory.llm_factory import LLMFactory
from prompts import ARMA_SUPERVISOR_PROMPT
from state import ARMAState

class ARMAWorkflow:
    """
    Encapsulates the ARMA workflow, including agent, LLM, prompt, state, store, and checkpoint initialization.
    Provides a method to compile and return the workflow.
    """
    def __init__(
        self,
        agents: Optional[List[Any]] = None,
        model: Optional[Any] = None,
        prompt: Optional[str] = None,
        supervisor_name: str = "arma_supervisor",
        state_schema: Optional[Any] = None,
        output_mode: str = "full_history",
        store: Optional[Any] = None,
        checkpoint: Optional[Any] = None,
        verbose: bool = True
    ):
        """
        Initialize the ARMAWorkflow with optional custom configuration.
        """
        self.logger = logging.getLogger("arma.ARMAWorkflow")
        self.verbose = verbose
        self.supervisor_name = supervisor_name
        self.output_mode = output_mode
        self.store = store or self._init_store()
        self.checkpoint = checkpoint or self._init_checkpoint()
        self.agents = agents or self._init_agents()
        self.model = model or self._init_llm()
        self.prompt = prompt or self._init_prompt()
        self.state_schema = state_schema or self._init_state_schema()
        if self.verbose:
            self.logger.info("ARMAWorkflow initialized.")

    def _init_agents(self) -> List[Any]:
        """Initialize and return the default list of agents."""
        if self.verbose:
            self.logger.info("Initializing default agents...")
        return [
            IntentAgent.build(),
            ValidationAgent.build(),
            ResourceActionAgent.build(),
            DeploymentAgent.build()
        ]

    def _init_llm(self) -> Any:
        """Initialize and return the default LLM/model."""
        if self.verbose:
            self.logger.info("Initializing default LLM/model...")
        return LLMFactory.get_llm()

    def _init_prompt(self) -> str:
        """Return the default supervisor prompt."""
        if self.verbose:
            self.logger.info("Using default supervisor prompt.")
        return ARMA_SUPERVISOR_PROMPT

    def _init_state_schema(self) -> Any:
        """Return the default state schema."""
        if self.verbose:
            self.logger.info("Using default state schema.")
        return ARMAState

    def _init_store(self) -> Any:
        """Return the default in-memory store."""
        if self.verbose:
            self.logger.info("Using default in-memory store.")
        return InMemoryStore()

    def _init_checkpoint(self) -> Any:
        """Return the default in-memory checkpoint saver."""
        if self.verbose:
            self.logger.info("Using default in-memory checkpoint saver.")
        return InMemorySaver()

    def compile_workflow(self) -> Any:
        """
        Create and compile the ARMA supervisor workflow with the current configuration.
        Returns the compiled workflow.
        """
        try:
            if self.verbose:
                self.logger.info("Creating supervisor workflow...")
            workflow = create_supervisor(
                self.agents,
                model=self.model,
                prompt=self.prompt,
                supervisor_name=self.supervisor_name,
                state_schema=self.state_schema,
                output_mode=self.output_mode
            )
            if self.verbose:
                self.logger.info("Compiling workflow...")
            arma = workflow.compile(store=self.store, checkpointer=self.checkpoint)
            if self.verbose:
                self.logger.info("ARMA workflow compiled successfully.")
            return arma
        except Exception as e:
            self.logger.error(f"Failed to create or compile ARMA workflow: {e}")
            raise

# Example usage:
# workflow = ARMAWorkflow()
# arma = workflow.compile_workflow()

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