"""
State schemas for the master graph.
"""

from typing import Optional, Literal, Annotated
from typing_extensions import TypedDict
from pydantic import Field
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class ARMAState(TypedDict):
    """
    State schema for the master graph.
    """
    messages: Annotated[list[AnyMessage], add_messages]
    prompt: str
    intent: Literal["create", "delete", "update", "get", "list"]
    resource_type: Optional[str]
    template: Optional[dict]
    location: Optional[str]
    scope: Optional[str]
    provided_fields: Optional[dict]
    resource_group_name: Optional[str]
    subscription_id: Optional[str]
    subscription_name: Optional[str]
    resource_group_exists: Optional[bool]
    resource_action_result: Optional[dict]
    resource_action_status: Optional[str]
    resource_action_error: Optional[str]
    subscription_exists: Optional[bool]
    missing_scope_fields: Optional[list]
    missing_scope_message: Optional[str]
    missing_parameters: Optional[list]
    parameter_file_content: Optional[dict]
    validation_result: Optional[dict]
    validation_status: Optional[str]
    validation_error: Optional[str]
    deployment_status: Optional[str]
    deployment_error: Optional[str]
    deployment_result: Optional[dict]
    remaining_steps: Optional[list]