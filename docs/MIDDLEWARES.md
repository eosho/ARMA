# ARMA Middlewares

Middlewares extend the agent with automatic capabilities that run before/after tool calls or model invocations.

## Available Middlewares

### PreflightMiddleware
**Purpose:** Validates Azure permissions and access control before deployments.

- Provides `validate_azure_context` tool to check subscription access and RBAC permissions
- Provides `check_resource_group` tool to verify resource group existence and access
- Preserves Azure context (subscription_id, resource_group, location) in state
- Configurable RBAC role validation and timeout settings

### TemplateDiscoveryMiddleware
**Purpose:** Automatically discovers Bicep templates after resource validation.

- Intercepts `check_existing_resource` tool calls
- Extracts resource type from tool results
- Automatically finds and analyzes matching Bicep templates
- Updates state with template path, parameters, and deployment scope
- Transparent operation - agent doesn't need explicit template discovery calls

### AzurePolicyComplianceMiddleware
**Purpose:** Validates deployments against Azure Policy before execution.

- Intercepts `plan_deployment` tool calls
- Retrieves policy assignments for the subscription/resource group
- Runs What-If analysis to detect policy violations
- Blocks deployments that would violate Deny policies
- Provides detailed violation messages with policy names and reasons

### TaggingMiddleware
**Purpose:** Automatically tags deployed Azure resources.

- Intercepts `execute_deployment` tool calls
- Tags resources after successful deployment with:
  - `deployer`: User ID who initiated deployment
  - `deployed_by`: Agent identifier (default: "arma-agent")
  - `deployed_at`: ISO 8601 timestamp
- Supports best-effort mode (logs failures) or strict mode (fails on tag errors)

### ConversationSummaryMiddleware
**Purpose:** Manages conversation memory by trimming old messages.

- Runs before model invocations
- Keeps most recent N messages (default: 20)
- Preserves system messages
- Prevents context window overflow

### UsageTrackingMiddleware
**Purpose:** Tracks LLM token consumption and costs.

- Runs after model invocations
- Tracks input/output tokens per call
- Maintains running totals across conversation
- Updates state with usage metadata

## Middleware Lifecycle

```
User Request
    ↓
[ConversationSummaryMiddleware] → before_model (trim history)
    ↓
Model Invocation
    ↓
[UsageTrackingMiddleware] → after_model (track tokens)
    ↓
Tool Call (e.g., check_existing_resource)
    ↓
[TemplateDiscoveryMiddleware] → after_tool (discover template)
    ↓
Tool Call (e.g., plan_deployment)
    ↓
[AzurePolicyComplianceMiddleware] → before_tool (validate policy)
    ↓
Tool Call (e.g., execute_deployment)
    ↓
[TaggingMiddleware] → after_tool (tag resources)
    ↓
Response to User
```

## Configuration

Middlewares are registered in [`ARMAAgentFactory`](../src/arma/agent/factory.py):

```python
from arma.agent.factory import ARMAAgentFactory

factory = ARMAAgentFactory(
    model="openai:gpt-4o",
    streaming=True
)
agent = factory.create_agent()
```

All middlewares are automatically included with sensible defaults.
