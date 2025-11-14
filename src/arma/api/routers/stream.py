"""Streaming router for real-time interactions."""

import json
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from arma.agent import create_streaming_agent
from arma.api.models import StreamRequest
from arma.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Global agent instance (reused across requests)
_streaming_agent = None


def get_streaming_agent():
    """Get or create streaming agent instance."""
    global _streaming_agent
    if _streaming_agent is None:
        _streaming_agent = create_streaming_agent()
    return _streaming_agent


async def stream_generator(request: StreamRequest):
    """Generate streaming response chunks.

    Yields:
        Server-Sent Events (SSE) formatted chunks
    """
    try:
        agent = get_streaming_agent()

        # Generate thread_id if not provided
        thread_id = request.thread_id or str(uuid.uuid4())
        config = RunnableConfig(configurable={"thread_id": thread_id})

        # Prepare input
        turn_input = {
            "messages": [{"role": "user", "content": request.message}],
            "user_id": request.user_id,
        }

        logger.info(f"Starting stream for thread={thread_id}")

        # Send thread_id first
        yield f"data: {json.dumps({'type': 'thread_id', 'thread_id': thread_id})}\n\n"

        # Stream agent response
        async for chunk in agent.astream(
            turn_input, config=config, stream_mode=["messages", "updates"]
        ):
            mode, data = chunk
            if mode == "messages" and data:
                message = data[0]
                content = getattr(message, "content", None)
                if content:
                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

        # Check for interrupts (HITL)
        state = await agent.aget_state(config)
        if state.next and "__interrupt__" in state.values:
            logger.info(f"Auto-approving HITL interrupt for thread={thread_id}")

            # Send interrupt notification
            yield f"data: {json.dumps({'type': 'interrupt', 'status': 'auto_approving'})}\n\n"

            interrupts = state.values.get("__interrupt__", [])
            if interrupts:
                # Auto-approve in API mode
                resume_payload = {"decisions": [{"type": "approve"}]}

                # Stream resumed response
                async for chunk in agent.astream(
                    Command(resume=resume_payload), config=config, stream_mode=["messages", "updates"]
                ):
                    mode, data = chunk
                    if mode == "messages" and data:
                        message = data[0]
                        content = getattr(message, "content", None)
                        if content:
                            yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

        # Send completion signal
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        logger.info(f"Stream completed for thread={thread_id}")

    except Exception as e:
        logger.error(f"Stream failed: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


@router.post("/stream")
async def stream(request: StreamRequest) -> StreamingResponse:
    """Stream agent responses in real-time using Server-Sent Events (SSE).

    This endpoint provides token-by-token streaming for real-time interactions.
    Automatically handles HITL approvals in the background.

    Args:
        request: Stream request containing message and optional thread_id

    Returns:
        StreamingResponse with SSE-formatted chunks

    Event Types:
        - thread_id: Initial event with thread_id
        - content: Token content chunks
        - interrupt: HITL interrupt notification
        - done: Stream completion signal
        - error: Error information

    Example:
        ```bash
        curl -X POST http://localhost:8000/chat/stream \
          -H "Content-Type: application/json" \
          -d '{"message": "deploy a storage account"}' \
          --no-buffer
        ```
    """
    return StreamingResponse(
        stream_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
