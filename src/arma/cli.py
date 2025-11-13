"""Interactive CLI for the ARMA deployment agent.

This module provides the command-line interface entry point for ARMA.

Usage:
    arma
"""

import asyncio
import uuid

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from arma.agent import create_arma_agent


async def run_agent() -> None:
    """Run interactive agent session with HITL approval for execute_deployment."""
    print("=" * 60)
    print("🚀 ARMA Agent")
    print("=" * 60)
    print("Type 'quit' or 'exit' to end the session\n")

    agent = create_arma_agent()
    thread_id = str(uuid.uuid4())
    config = RunnableConfig(configurable={"thread_id": thread_id})

    print(f"📝 Session ID: {thread_id}\n")

    # Track if this is the first turn
    is_first_turn = True

    while True:
        try:
            # Get user input
            user_input = input("\n👤 You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "bye"]:
                print("\n👋 Thanks for using ARMA! Goodbye!")
                break

            # For first turn, include initial state with user_id
            # For subsequent turns, only send the new message - checkpointer restores the rest
            if is_first_turn:
                turn_input = {
                    "messages": [{"role": "user", "content": user_input}],
                    "user_id": "test-user@example.com",  # Set on first turn for tagging
                }
                is_first_turn = False
            else:
                turn_input = {"messages": [{"role": "user", "content": user_input}]}

            print("\n🤔 Agent thinking...\n")

            # Invoke agent/graph with checkpoint config
            result = await agent.ainvoke(turn_input, config=config)

            # Check for interrupts (Human-in-the-Loop)
            if "__interrupt__" in result:
                interrupts = result["__interrupt__"]
                if interrupts:
                    interrupt = interrupts[0]
                    print("\n" + "=" * 50)
                    print("HUMAN APPROVAL REQUIRED")
                    print("=" * 50)

                    # Extract action request details
                    value = interrupt.value if hasattr(interrupt, "value") else interrupt

                    # Handle different interrupt value structures
                    action_requests = []
                    if isinstance(value, dict):
                        action_requests = value.get("action_requests", [])
                    elif isinstance(value, list):
                        action_requests = value

                    for req in action_requests:
                        # Extract tool name from different possible locations
                        tool_name = (
                            req.get("tool")
                            or req.get("action")
                            or req.get("name")
                            or req.get("tool_call", {}).get("name")
                            or "unknown"
                        )

                        description = req.get("description", "Booking action pending approval")

                        print(f"\nAction: {tool_name}")
                        print(f"Description: {description}")

                    # Get user decision
                    decision = input("\nDecision ([a]pprove/[r]eject): ").strip().lower()

                    # Build resume payload based on decision
                    if decision.startswith("a"):
                        resume_payload = {"decisions": [{"type": "approve"}]}
                        print("\nApproved - resuming execution...")
                    elif decision.startswith("r"):
                        resume_payload = {"decisions": [{"type": "reject"}]}
                        print("\nRejected - cancelling action...")
                    else:
                        resume_payload = {"decisions": [{"type": "reject"}]}
                        print("\nUnrecognized decision - defaulting to reject...")

                    # Resume with decision
                    result = await agent.ainvoke(Command(resume=resume_payload), config=config)

            final_response = result

            # Print all messages to see tool calls and intermediate steps
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
    asyncio.run(run_agent())


if __name__ == "__main__":
    main()
