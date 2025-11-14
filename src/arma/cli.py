"""Interactive CLI for the ARMA deployment agent.

This module provides the command-line interface entry point for ARMA.

Usage:
    arma                              # Interactive mode
    arma --stream                     # Interactive mode with streaming
    arma --query "your question"      # Single query mode
    arma --stream --query "question"  # Single query with streaming
"""

import argparse
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


async def run_agent_streaming(query: str | None = None) -> None:
    """Run streaming agent session.

    Args:
        query: Optional single query to run. If None, runs interactive mode.
    """
    if not query:
        _print_banner(streaming=True)

    agent = create_streaming_agent()
    thread_id = str(uuid.uuid4())
    config = RunnableConfig(configurable={"thread_id": thread_id})

    if not query:
        print(f"📝 Session ID: {thread_id}\n")

    is_first_turn = True

    # Single query mode
    if query:
        turn_input = _prepare_turn_input(query, is_first_turn)

        last_content = ""
        async for chunk in agent.astream(turn_input, config=config, stream_mode=["values"]):
            mode, data = chunk
            if mode == "values" and isinstance(data, dict):
                messages = data.get("messages", [])
                if messages:
                    # Get the last AI message only
                    for message in reversed(messages):
                        if getattr(message, "type", None) == "ai" or message.__class__.__name__ == "AIMessage":
                            content = getattr(message, "content", None)
                            if content and content != last_content:
                                # Print only the new content
                                new_content = content[len(last_content):]
                                print(new_content, end="", flush=True)
                                last_content = content
                            break

        print("\n")

        # Check for interrupts (HITL)
        final_state = await agent.aget_state(config)
        if final_state.next and "__interrupt__" in final_state.values:
            interrupts = final_state.values.get("__interrupt__", [])
            if interrupts:
                interrupt = interrupts[0]
                resume_payload = _handle_approval_request(interrupt)

                print("\n🤖 Agent:\n")
                async for chunk in agent.astream(
                    Command(resume=resume_payload), config=config, stream_mode=["messages", "updates"]
                ):
                    mode, data = chunk
                    if mode == "messages" and data:
                        message = data[0]
                        content = getattr(message, "content", None)
                        if content:
                            print(content, end="", flush=True)

                print("\n")
        return

    # Interactive mode
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

            print("\n🤖 Agent:\n")

            async for chunk in agent.astream(turn_input, config=config, stream_mode=["messages"]):
                mode, data = chunk
                if mode == "messages":
                    message = data[0]
                    content = (
                        getattr(message, "content", None) or message
                        if isinstance(message, str)
                        else None
                    )
                    if content:
                        print(content, end="", flush=True)

            print("\n")

            # Check for interrupts (HITL)
            state = await agent.aget_state(config)
            if state.next and "__interrupt__" in state.values:
                interrupts = state.values.get("__interrupt__", [])
                if interrupts:
                    interrupt = interrupts[0]
                    resume_payload = _handle_approval_request(interrupt)

                    print("\n🤖 Agent:\n")
                    async for chunk in agent.astream(
                        Command(resume=resume_payload), config=config, stream_mode=["messages"]
                    ):
                        mode, data = chunk
                        if mode == "messages":
                            message = data[0]
                            content = (
                                getattr(message, "content", None) or message
                                if isinstance(message, str)
                                else None
                            )
                            if content:
                                print(content, end="", flush=True)

                    print("\n")

        except KeyboardInterrupt:
            print("\n\n👋 Session interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback

            traceback.print_exc()


async def run_agent(query: str | None = None) -> None:
    """Run agent session with HITL approval.

    Args:
        query: Optional single query to run. If None, runs interactive mode.
    """
    if not query:
        _print_banner()

    agent = create_arma_agent()
    thread_id = str(uuid.uuid4())
    config = RunnableConfig(configurable={"thread_id": thread_id})

    if not query:
        print(f"📝 Session ID: {thread_id}\n")

    is_first_turn = True

    # Single query mode
    if query:
        turn_input = _prepare_turn_input(query, is_first_turn)
        result = await agent.ainvoke(turn_input, config=config)

        if "__interrupt__" in result:
            interrupts = result["__interrupt__"]
            if interrupts:
                interrupt = interrupts[0]
                resume_payload = _handle_approval_request(interrupt)
                result = await agent.ainvoke(Command(resume=resume_payload), config=config)

        # Print final response
        if result.get("messages"):
            last_message = result["messages"][-1]
            if hasattr(last_message, "content"):
                print(f"\n🤖 Agent: {last_message.content}\n")
        return

    # Interactive mode
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
    parser = argparse.ArgumentParser(
        description="ARMA - Azure Resource Management Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  arma                                    # Interactive mode
  arma --stream                           # Interactive with streaming
  arma --query "deploy storage account"  # Single query
  arma -s -q "check my resources"        # Single query with streaming
        """,
    )

    parser.add_argument(
        "-s",
        "--stream",
        action="store_true",
        help="Enable streaming mode for real-time token output",
    )

    parser.add_argument(
        "-q", "--query", type=str, help="Run a single query instead of interactive mode"
    )

    args = parser.parse_args()

    if args.stream:
        asyncio.run(run_agent_streaming(query=args.query))
    else:
        asyncio.run(run_agent(query=args.query))


if __name__ == "__main__":
    main()
