"""Azure Resource Management Assistant (ARMA) agent factory."""

from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelRequest,
    TodoListMiddleware,
    dynamic_prompt,
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from arma.agent.llm.registry import get_llm
from arma.agent.middleware import (
    ConversationSummaryMiddleware,
    PreflightMiddleware,
    TaggingMiddleware,
    TemplateDiscoveryMiddleware,
    UsageTrackingMiddleware,
)
from arma.agent.state import ARMAAgentState
from arma.agent.tools import (
    delete_resource,
    execute_deployment,
    get_arma_version,
    get_current_date,
    get_resource,
    list_resources,
    plan_deployment,
    preview_what_if,
    update_resource_tags,
)

from .prompt import ARMA_SYSTEM_PROMPT


class ARMAAgentFactory:
    """Factory for creating Azure Resource Management Assistant agents."""

    def create(self) -> CompiledStateGraph:
        """Create a configured deployment agent.

        Returns:
            A configured LangChain agent with checkpointer for HITL support

        Example:
            >>> factory = ARMAAgentFactory()
            >>> agent = factory.create()
            >>> result = agent.invoke({"messages": [...]})
        """
        llm = get_llm()

        tools = [
            delete_resource,
            execute_deployment,
            get_resource,
            get_arma_version,
            get_current_date,
            list_resources,
            plan_deployment,
            preview_what_if,
            update_resource_tags,
        ]

        middleware = self._build_middleware()

        return create_agent(
            model=llm,
            tools=tools,
            state_schema=ARMAAgentState,
            middleware=middleware,
            checkpointer=MemorySaver(),
        )

    def _build_middleware(self) -> list:
        """Build the middleware stack.

        Returns:
            List of configured middleware instances
        """

        @dynamic_prompt
        def deployment_prompt(request: ModelRequest) -> str:
            """Inject context into base system prompt."""
            prompt = ARMA_SYSTEM_PROMPT
            user_name = getattr(request.runtime.context, "user_name", "")
            msg_count = len(request.state["messages"])

            additions = []
            if user_name:
                additions.append(f"User's name: {user_name}")
            if msg_count > 10:
                additions.append("Long conversation - be concise")

            return f"{prompt}\n\n## Context\n{' | '.join(additions)}" if additions else prompt

        return [
            deployment_prompt,
            PreflightMiddleware(),
            TodoListMiddleware(
                system_prompt="For complex Azure deployments, use write_todos to break down steps: analyze, plan, validate, execute"
            ),
            ConversationSummaryMiddleware(max_messages=30),
            TemplateDiscoveryMiddleware(),
            TaggingMiddleware(
                user_id_key="user_id",
                agent_name="arma-agent",
                mode="best-effort",
                enabled=True,
            ),
            UsageTrackingMiddleware(),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "execute_deployment": {"allowed_decisions": ["approve", "reject"]},
                    "delete_resource": {"allowed_decisions": ["approve", "reject"]},
                },
                description_prefix="Approval required for execute deployment",
            ),
        ]


def create_arma_agent() -> CompiledStateGraph:
    """Create an ARMA deployment agent.

    This is a helper function that creates and configures a deployment agent
    using the ARMAAgentFactory.

    Returns:
        A configured LangChain agent with checkpointer for HITL support

    Example:
        >>> from arma.agent import create_arma_agent
        >>> from langchain_core.runnables import RunnableConfig
        >>>
        >>> agent = create_arma_agent()
        >>>
        >>> # Run agent with initial state
        >>> config = RunnableConfig(configurable={"thread_id": "test-123"})
        >>> state = {"messages": [{"role": "user", "content": "Deploy a storage account"}]}
        >>> result = agent.invoke(state, config)
    """
    factory = ARMAAgentFactory()
    return factory.create()
