<table>
  <tr>
    <td width="110">
      <img src="./arma_logo.png" alt="ARMA Logo" width="200"/>
    </td>
    <td>
      <h1>Azure Resource Management Assistant (ARMA)</h1>
      <p>ARMA is a modular, multi-agent assistant for Azure resource provisioning, validation, and management, built with LangGraph and LangChain v1.</p>
    </td>
  </tr>
</table>

## Table of Contents

- [TL;DR](#tldr)
- [Features](#features)
- [Architecture](#architecture)
  - [System Flow](#system-flow)
  - [Middleware Stack](#middleware-stack)
  - [Agent Tools](#agent-tools)
- [Quickstart](#quickstart)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Run the Agent](#run-the-agent)
- [Usage Examples](#usage-examples)
- [Development](#development)
  - [Project Structure](#project-structure)
  - [Running Tests](#running-tests)
  - [Code Quality](#code-quality)
- [Bicep Templates](#bicep-templates)
- [Contributing](#contributing)
- [License](#license)


---

## TL;DR

**What it does:** ARMA is an AI-powered assistant that helps you deploy and manage Azure resources using natural language. It translates your requests into validated Bicep templates, provides what-if analysis, and executes deployments with human-in-the-loop approval.

**Who it's for:** DevOps engineers, cloud architects, and developers who want to streamline Azure infrastructure management without writing IaC manually.

**Quick start:**
```bash
git clone https://github.com/eosho/arma.git && cd arma
uv sync
uv run poe dev-agent
```

---

## Features

- **🗣️ Natural Language Interface** - Describe what you want in plain English
- **🔍 Intelligent Template Discovery** - Automatically finds and configures Bicep templates
- **📊 What-If Analysis** - Preview changes before deployment with Azure's native what-if API
- **✅ Human-in-the-Loop (HITL)** - Approve/reject sensitive operations before execution
- **🏷️ Automatic Tagging** - Tags deployed resources with metadata (user, timestamp, agent)
- **💾 Conversation Memory** - Maintains context across multiple interactions
- **📝 TODO Planning** - Breaks down complex deployments into manageable steps
- **🔐 Azure-Native Auth** - Uses `DefaultAzureCredential` via the Azure CLI


---

## Architecture

### System Flow

```mermaid
sequenceDiagram
    actor User
    participant Agent as ARMA Agent<br/>(LangGraph)
    participant Middleware as Middleware Stack
    participant Tools as Agent Tools
    participant Azure as Azure Services

    User->>Agent: "Deploy storage account 'mystorageacct' in test-rg"
    activate Agent

    Agent->>Middleware: Preflight Validation
    Middleware-->>Agent: Context enriched

    Agent->>Middleware: Template Discovery
    Middleware-->>Agent: Bicep template located

    Agent->>Tools: plan_deployment(resource_type, params)
    activate Tools
    Tools->>Azure: Query Resource Graph
    Azure-->>Tools: Existing resources
    Tools-->>Agent: Deployment plan created
    deactivate Tools

    Agent->>Tools: preview_what_if(template, params)
    activate Tools
    Tools->>Azure: What-If API call
    Azure-->>Tools: Predicted changes
    Tools-->>Agent: Impact analysis
    deactivate Tools

    Agent-->>User: 🛑 Approval Required<br/>Preview changes
    User->>Agent: Approve

    Agent->>Tools: execute_deployment(template, params)
    activate Tools
    Tools->>Azure: Bicep compile
    Azure-->>Tools: ARM template
    Tools->>Azure: Deployment API
    Azure-->>Tools: Deployment in progress
    Tools-->>Agent: Deployment initiated
    deactivate Tools

    Agent->>Middleware: Apply resource tags
    Middleware->>Azure: Tag resources

    Agent-->>User: ✅ Deployment completed
    deactivate Agent
```

**Key Components:**
- **Agent State**: Tracks Azure context, deployment plans, validation results
- **Tools**: Modular functions for Azure operations (query, plan, execute, delete)
- **Middleware**: Interceptors that enhance agent capabilities (see below)
- **Checkpointer**: Persists conversation state for HITL and resumability

### Middleware Stack

ARMA uses a middleware architecture to intercept and enhance agent requests. Middleware components are located in `src/arma/agent/middleware/`:

| Middleware | Purpose | Location |
|-----------|---------|----------|
| **Preflight Validation** | Validates Azure credentials and context before execution | `pre_flight.py` |
| **Template Discovery** | Automatically finds and suggests appropriate Bicep templates | `template_discovery.py` |
| **Conversation Summary** | Maintains conversation context and summarizes long histories | `conversation_summary.py` |
| **Resource Tagging** | Automatically tags deployed resources with metadata (user, timestamp, agent) | `tagging.py` |
| **Usage Tracking** | Monitors tool usage, token consumption, and performance metrics | `usage_tracking.py` |
| **Template Discovery** | Automatically finds appropriate Bicep templates from local store | `template_discovery.py` |

Each middleware implements hooks like `before_agent`, `before_model`, `after_model`, etc. to intercept and modify the agent's behavior at different stages of execution.

### Agent Tools

ARMA's agent tools are implemented in `src/arma/agent/tools/`:

| Tool | Purpose | Location |
|------|---------|----------|
| **check_existing_resource** | Checks if a resource exists in Azure and triggers template discovery | `pre_flight.py` (middleware) |
| **create_resource_group** | Creates or validates resource group existence | `pre_flight.py` (middleware) |
| **plan_deployment** | Compiles Bicep to ARM, merges parameters, and creates deployment plan | `plan.py` |
| **preview_what_if** | Runs Azure what-if analysis to preview deployment changes | `plan.py` |
| **execute_deployment** | Executes the deployment plan (requires HITL approval) | `execute.py` |
| **list_resources** | Lists Azure resources by type with optional filters | `query.py` |
| **get_resource** | Gets detailed information about a specific resource | `query.py` |
| **delete_resource** | Deletes an Azure resource (requires HITL approval) | `query.py` |
| **update_resource_tags** | Updates or replaces tags on an existing resource | `query.py` |
| **get_arma_version** | Returns the current ARMA version | `generic.py` |
| **get_current_date** | Returns the current date and time | `generic.py` |

---

## Quickstart

### Prerequisites

- **Python 3.11+** (3.12 recommended)
- **uv** package manager ([install](https://github.com/astral-sh/uv))
- **Azure CLI** with active login (`az login`)
- **Azure OpenAI** or **OpenAI API** key

### Installation

```bash
# Clone the repository
git clone https://github.com/eosho/arma.git
cd arma

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env

# Configure your .env file
# Required: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT
# Or: OPENAI_API_KEY (for OpenAI instead of Azure OpenAI)
```

### Configuration

Create a `.env` file in the project root:

```bash
# Azure OpenAI (recommended)
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4  # Your deployment name
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# OR OpenAI (alternative)
# OPENAI_API_KEY=sk-...

# Optional: LangSmith tracing
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=your-langsmith-key
# LANGSMITH_PROJECT=arma-dev

# Optional: Database for persistence (future)
# DATABASE_URL=postgresql://user:pass@localhost:5432/arma
```

### Run the Agent

```bash
# Interactive CLI
uv run poe dev-agent

# Or directly
python run_arma.py
```

**Example interaction:**
```
🚀 ARMA Agent
============================================================
Type 'quit' or 'exit' to end the session

👤 You: Deploy a storage account named mystorageacct in resource group test-rg

🤔 Agent thinking...

[Agent discovers template, validates parameters, generates deployment plan]

============================================================
HUMAN APPROVAL REQUIRED
============================================================

Action: execute_deployment
Description: Deploy Bicep template for Microsoft.Storage/storageAccounts

Decision ([a]pprove/[r]eject): a

✅ Deployment completed successfully!
```

---

## Usage Examples

### List Resources
```
👤 You: List all storage accounts in my subscription

💡 Agent: Found 3 storage accounts:
   - mystorageacct (eastus, Standard_LRS)
   - proddata001 (westus2, Standard_GRS)
   - devlogs (eastus2, Standard_LRS)
```

### What-If Analysis
```
👤 You: What would happen if I deployed a VM in test-rg?

💡 Agent: Running what-if analysis...
   Changes:
   + Microsoft.Compute/virtualMachines/testvm
   + Microsoft.Network/networkInterfaces/testvm-nic
   + Microsoft.Network/publicIPAddresses/testvm-ip
```

### Delete Resource
```
👤 You: Delete storage account mystorageacct

⚠️  APPROVAL REQUIRED
   Action: delete_resource
   Resource: /subscriptions/.../storageAccounts/mystorageacct

Decision: approve
✅ Resource deleted successfully
```

---

## Development

### Project Structure

```
arma/
├── src/arma/              # Main package
│   ├── agent/             # Agent logic
│   │   ├── factory.py     # Agent factory
│   │   ├── prompt.py      # System prompts
│   │   ├── state/         # State schemas
│   │   ├── tools/         # Agent tools
│   │   └── middleware/    # Middleware stack
│   ├── core/              # Core utilities
│   │   ├── config.py      # Configuration
│   │   └── logging.py     # Logging setup
│   └── models/            # Database models (future)
├── bicep/                 # Bicep templates
│   └── modules/           # Modular templates by resource type
└── pyproject.toml         # Project metadata
```

### Running Tests

```bash
# Run all tests
uv run poe test

# Unit tests only
uv run poe test-unit

# With coverage
uv run poe test-cov
```

### Code Quality

```bash
# Format code
uv run poe format

# Lint
uv run poe lint

# Type checking
uv run poe typecheck

# Run all quality checks
uv run poe quality
```

---

## Bicep Templates

ARMA uses a modular Bicep template library organized by Azure resource provider:

```
bicep/modules/
├── Microsoft.Storage/
│   └── storageAccounts/
│       └── main.bicep
├── Microsoft.Compute/
│   └── virtualMachines/
│       └── main.bicep
└── ...
```

Templates are automatically discovered based on resource type. To add a new template:

1. Create folder: `bicep/modules/{Provider}/{ResourceType}/`
2. Add `main.bicep` with parameters
3. ARMA will auto-discover it via `TemplateDiscoveryMiddleware`

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Ensure tests pass and code is formatted:
```bash
uv run poe quality
uv run poe test
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**Made with ❤️ by the ARMA Team**
