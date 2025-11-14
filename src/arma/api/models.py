"""API models for ARMA endpoints."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Chat message model."""

    role: Literal["user", "assistant", "system"] = Field(description="Role of the message sender")
    content: str = Field(description="Content of the message")


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(description="User message to send to the agent")
    thread_id: str | None = Field(default=None, description="Thread ID for conversation continuity")
    user_id: str = Field(default="api-user@example.com", description="User identifier for tracking")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    response: str = Field(description="Agent's response message")
    thread_id: str = Field(description="Thread ID for this conversation")
    usage: dict | None = Field(default=None, description="Token usage information")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(description="Service status")
    version: str = Field(description="ARMA version")
