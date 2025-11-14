"""Interactive CLI for the ARMA deployment agent.

This module provides the command-line interface entry point for ARMA.

Usage:
    arma (non stream)
    arma -s | --stream (streaming enabled)
"""

import asyncio
import uuid

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from arma.agent import create_arma_agent, create_streaming_agent


def _prepare_turn_input(user_input: str, is_first_turn: bool) -> dict:
    """Prepare input for agent turn.

    Args:
        user_input: User message content
        is_first_turn: Whether this is the first turn (includes user_id)

    Returns:
        Input dict for agent
    """
    if is_first_turn:
        return {
            "messages": [{"role": "user", "content": user_input}],
            "user_id": "test-user@example.com",
        }
    else:
        return {"messages": [{"role": "user", "content": user_input}]}


def _print_banner(streaming: bool = False) -> None:
    """Print CLI banner.

    Args:
        streaming: Whether streaming mode is enabled
    """
    print("=" * 60)
    if streaming:
        print("🚀 ARMA Agent (Streaming)")
    else:
        print("🚀 ARMA Agent")
    print("=" * 60)
    print("Type 'quit' or 'exit' to end the session\n")


def _handle_approval_request(interrupt) -> dict:
    """Handle human-in-the-loop approval request.

    Args:
        interrupt: Interrupt object containing action requests

    Returns:
        Resume payload with approval decision
    """
    print("\n" + "=" * 50)
    print("⏸️  HUMAN APPROVAL REQUIRED")
    print("=" * 50)

    value = interrupt.value if hasattr(interrupt, "value") else interrupt

    action_requests = []
    if isinstance(value, dict):
        action_requests = value.get("action_requests", [])
    elif isinstance(value, list):
        action_requests = value

    for req in action_requests:
        tool_name = (
            req.get("tool")
            or req.get("action")
            or req.get("name")
            or req.get("tool_call", {}).get("name")
            or "unknown"
        )
        description = req.get("description", "Action pending approval")
        print(f"\nAction: {tool_name}")
        print(f"Description: {description}")

    decision = input("\nDecision ([a]pprove/[r]eject): ").strip().lower()

    if decision.startswith("a"):
        print("\n✅ Approved - resuming execution...")
        return {"decisions": [{"type": "approve"}]}
    else:
        print("\n❌ Rejected - cancelling action...")
        return {"decisions": [{"type": "reject"}]}


async def run_agent_streaming() -> None:
    """Run interactive streaming agent session."""
    _print_banner(streaming=True)

    agent = create_streaming_agent()
    thread_id = str(uuid.uuid4())
    config = RunnableConfig(configurable={"thread_id": thread_id})

    print(f"📝 Session ID: {thread_id}\n")

    is_first_turn = True

    while True:
        try:
            user_input = input("\n👤 You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "bye"]:
                print("\n👋 Thanks for using ARMA! Goodbye!")
                break

            turn_input = _prepare_turn_input(user_input, is_first_turn)
            if is_first_turn:
                is_first_turn = False

            print("\n🤖 Agent:\n", end="", flush=True)

            final_result = None

            async for chunk in agent.astream(
                turn_input, config=config, stream_mode=["messages", "values"]
            ):
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    mode, data = chunk

                    if mode == "messages" and isinstance(data, tuple) and len(data) == 2:
                        message_chunk, metadata = data

                        # Simple raw output for all message types
                        if hasattr(message_chunk, "content") and message_chunk.content:
                            print(message_chunk.content, end="", flush=True)

                    elif mode == "values" and isinstance(data, dict):
                        final_result = data

                        if "__interrupt__" in data:
                            interrupts = data["__interrupt__"]
                            if interrupts:
                                interrupt = interrupts[0]
                                resume_payload = _handle_approval_request(interrupt)

                                print("\n\n🤖 Agent:\n", end="", flush=True)

                                async for resume_chunk in agent.astream(
                                    Command(resume=resume_payload),
                                    config=config,
                                    stream_mode=["messages", "values"],
                                ):
                                    if isinstance(resume_chunk, tuple) and len(resume_chunk) == 2:
                                        resume_mode, resume_data = resume_chunk

                                        if (
                                            resume_mode == "messages"
                                            and isinstance(resume_data, tuple)
                                            and len(resume_data) == 2
                                        ):
                                            message_chunk, metadata = resume_data
                                            if (
                                                hasattr(message_chunk, "content")
                                                and message_chunk.content
                                            ):
                                                print(message_chunk.content, end="", flush=True)

                                        elif resume_mode == "values" and isinstance(
                                            resume_data, dict
                                        ):
                                            final_result = resume_data

            print("\n")

        except KeyboardInterrupt:
            print("\n\n👋 Session interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback

            traceback.print_exc()


async def run_agent() -> None:
    """Run interactive agent session with HITL approval."""
    _print_banner()

    agent = create_arma_agent()
    thread_id = str(uuid.uuid4())
    config = RunnableConfig(configurable={"thread_id": thread_id})

    print(f"📝 Session ID: {thread_id}\n")

    is_first_turn = True

    while True:
        try:
            user_input = input("\n👤 You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "bye"]:
                print("\n👋 Thanks for using ARMA! Goodbye!")
                break

            turn_input = _prepare_turn_input(user_input, is_first_turn)
            if is_first_turn:
                is_first_turn = False

            print("\n🤔 Agent thinking...\n")

            result = await agent.ainvoke(turn_input, config=config)

            if "__interrupt__" in result:
                interrupts = result["__interrupt__"]
                if interrupts:
                    interrupt = interrupts[0]
                    resume_payload = _handle_approval_request(interrupt)

                    result = await agent.ainvoke(Command(resume=resume_payload), config=config)

            final_response = result

            print("\n" + "=" * 50)
            print("💭 CONVERSATION TRACE:")
            print("=" * 50)
            for i, msg in enumerate(final_response["messages"]):
                print(f"\n[Message {i+1}]")
                msg.pretty_print()

        except KeyboardInterrupt:
            print("\n\n👋 Session interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback

            traceback.print_exc()


def main() -> None:
    """Entry point for the arma CLI command."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ["--stream", "-s"]:
        asyncio.run(run_agent_streaming())
    else:
        asyncio.run(run_agent())


if __name__ == "__main__":
    main()
