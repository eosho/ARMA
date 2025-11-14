# ARMA Middlewares

For comprehensive documentation on ARMA middlewares, see [MIDDLEWARES.md](/home/groot/ARMA/docs/MIDDLEWARES.md).

## Quick Overview

ARMA uses 6 middlewares to extend agent capabilities:

- **PreflightMiddleware** - Validates Azure permissions and access control
- **TemplateDiscoveryMiddleware** - Automatically discovers Bicep templates
- **AzurePolicyComplianceMiddleware** - Validates deployments against Azure Policy
- **TaggingMiddleware** - Automatically tags deployed resources
- **ConversationSummaryMiddleware** - Manages conversation memory
- **UsageTrackingMiddleware** - Tracks LLM token consumption

All middlewares are automatically included when creating an agent via `ARMAAgentFactory`.
