"""Chat router for non-streaming interactions."""

import uuid

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from arma.agent import create_arma_agent
from arma.api.models import ChatRequest, ChatResponse
from arma.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Global agent instance (reused across requests)
_agent = None


def get_agent():
    """Get or create agent instance."""
    global _agent
    if _agent is None:
        _agent = create_arma_agent()
    return _agent


@router.post("/ask", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a chat message and return the agent's response.

    This endpoint handles non-streaming interactions with the ARMA agent.
    Supports human-in-the-loop (HITL) approval flows automatically.

    Args:
        request: Chat request containing message and optional thread_id

    Returns:
        ChatResponse with agent's message and thread_id

    Raises:
        HTTPException: If agent processing fails
    """
    try:
        agent = get_agent()

        # Generate thread_id if not provided
        thread_id = request.thread_id or str(uuid.uuid4())
        config = RunnableConfig(configurable={"thread_id": thread_id})

        # Prepare input
        turn_input = {
            "messages": [HumanMessage(content=request.message)],
            "user_id": request.user_id,
        }

        logger.info(f"Processing chat request for thread={thread_id}")

        # Invoke agent
        result = await agent.ainvoke(turn_input, config=config)

        # Handle interrupts (HITL) - auto-approve for API
        if "__interrupt__" in result:
            logger.info(f"Auto-approving HITL interrupt for thread={thread_id}")
            interrupts = result["__interrupt__"]
            if interrupts:
                # Auto-approve all actions in API mode
                resume_payload = {"decisions": [{"type": "approve"}]}
                result = await agent.ainvoke(Command(resume=resume_payload), config=config)

        # Extract response
        messages = result.get("messages", [])
        if not messages:
            raise HTTPException(status_code=500, detail="No response from agent")

        last_message = messages[-1]
        response_content = (
            last_message.content if hasattr(last_message, "content") else str(last_message)
        )

        # Extract usage info if available
        usage = result.get("usage_metadata")

        logger.info(f"Chat request completed for thread={thread_id}")

        return ChatResponse(response=response_content, thread_id=thread_id, usage=usage)

    except Exception as e:
        logger.error(f"Chat request failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}") from e
