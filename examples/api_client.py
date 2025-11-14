"""Example API client for testing ARMA endpoints."""

import asyncio

import httpx


async def test_chat():
    """Test the chat endpoint."""
    print("Testing /chat/ask endpoint...")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "http://localhost:8000/chat/ask",
            json={
                "message": "What version of ARMA am I using?",
                "user_id": "test-user@example.com",
            },
        )

        if response.status_code == 200:
            data = response.json()
            print("\n✅ Chat Response:")
            print(f"Thread ID: {data['thread_id']}")
            print(f"Response: {data['response']}")
            if data.get("usage"):
                print(f"Usage: {data['usage']}")
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")


async def test_stream():
    """Test the streaming endpoint."""
    print("\nTesting /chat/stream endpoint...")
    print("\n🤖 Streaming response:")

    async with (
        httpx.AsyncClient(timeout=120.0) as client,
        client.stream(
            "POST",
            "http://localhost:8000/chat/stream",
            json={
                "message": "Tell me about ARMA in one sentence",
                "user_id": "test-user@example.com",
            },
        ) as response,
    ):
        if response.status_code == 200:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    import json

                    data = json.loads(line[6:])

                    if data["type"] == "thread_id":
                        print(f"\nThread ID: {data['thread_id']}\n")
                    elif data["type"] == "content":
                        print(data["content"], end="", flush=True)
                    elif data["type"] == "interrupt":
                        print(f"\n[HITL: {data['status']}]", flush=True)
                    elif data["type"] == "done":
                        print("\n\n✅ Stream completed")
                    elif data["type"] == "error":
                        print(f"\n❌ Error: {data['error']}")
        else:
            print(f"❌ Error: {response.status_code}")


async def main():
    """Run API tests."""
    print("=" * 60)
    print("ARMA API Client Test")
    print("=" * 60)

    try:
        # Test health endpoint
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ API Health: {data['status']} (v{data['version']})\n")
            else:
                print("❌ API not available")
                return

        # Test chat endpoint
        await test_chat()

        # Test streaming endpoint
        await test_stream()

    except httpx.ConnectError:
        print("❌ Could not connect to API. Make sure it's running:")
        print("   uv run poe dev-api")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
