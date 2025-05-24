# Azure Provisioning Workflow (LangGraph + LangChain)

## Overview

This project implements a **modular, production-grade, multi-agent workflow** for Azure resource provisioning using [LangGraph](https://github.com/langchain-ai/langgraph) and [LangChain](https://github.com/langchain-ai/langchain). It features robust conversational state management, full message logging (user, agent, and system/progress messages), and real-time UI display of all agent progress and interactions. The system is designed for extensibility, reliability, and seamless integration with modern UIs (Gradio, Streamlit, Chainlit).

---

## Table of Contents

- [Architecture](#architecture)
- [State Management](#state-management)
- [Agent & Subgraph Design](#agent--subgraph-design)
  - [Intent Detection Subgraph](#intent-detection-subgraph)
  - [Template Validation Subgraph](#template-validation-subgraph)
  - [Deployment Subgraph](#deployment-subgraph)
  - [Resource Action Agent](#resource-action-agent)
- [Main Graph Wiring](#main-graph-wiring)
- [Message Logging & UI Integration](#message-logging--ui-integration)
- [ARM Template Storage](#arm-template-storage)
- [How to Run](#how-to-run)
- [Extending the System](#extending-the-system)
- [File Structure](#file-structure)
- [Appendix: Example Conversation Flow](#appendix-example-conversation-flow)
- [Work In Progress (WIP)](#work-in-progress-wip)

---

## Architecture

The workflow is composed of three main subgraphs (agents), each responsible for a distinct phase of the Azure provisioning process:

1. **Intent Detection**: Extracts user intent, resource type, and relevant fields from natural language.
2. **Template Validation**: Validates user-provided fields against ARM template requirements.
3. **Deployment**: Deploys the validated template to Azure, handling both resource group and subscription scopes.

These subgraphs are orchestrated by a **master graph** (`graph.py`), which manages the overall workflow and state transitions.

---

## State Management

All conversational and workflow state is managed via a single, strongly-typed state object (`MasterState` in `state_schemas.py`). This state includes:

- `messages`: **Full conversation history** (user, agent, and system/progress messages)
- `intent`, `resource_type`, `provided_fields`, `resource_group_name`, `subscription_id`, `subscription_name`, `location`
- `template`, `scope`, `parameter_file_content`, `validation_error`, `deployment_status`, etc.

**All user and agent/system interactions are logged in the `messages` list**, ensuring the UI can display the complete conversation and agent progress in real time.

---

## Agent & Subgraph Design

### 1. Intent Detection Subgraph (`agents/intent_detection_langgraph.py`)

**Purpose:**  
Extracts the user's intent, Azure resource type, and all relevant fields from the user's natural language input.

**Nodes:**

- `intent_extraction`: Uses an LLM (Azure OpenAI) to extract intent, resource type, and fields.
- `scope_fields_check`: Ensures required fields (resource group, subscription) are present; interrupts if missing.
- `template_fetch`: Loads the correct ARM template based on resource type.
- `scope_determination`: Determines deployment scope (resource group, subscription, etc.) from the template schema.

**Flow:**

```mermaid
flowchart TD
    START([START]) --> intent_extraction
    intent_extraction --> scope_fields_check
    scope_fields_check --> decision{intent}
    decision -- create/update --> template_fetch
    decision -- get/list/delete --> END([END])
    template_fetch --> scope_determination
    scope_determination --> END([END])
```

**Key Features:**

- Uses a detailed system prompt with examples for robust extraction.
- Handles edge cases (e.g., GUID vs. name for subscription).
- Interrupts and prompts user if required fields are missing.

---

### 2. Template Validation Subgraph (`agents/template_validation_agent.py`)

**Purpose:**
Validates that all required ARM template parameters are provided and correct, using both code and LLM-based validation.

**Nodes:**

- `check_subscription`: Verifies the Azure subscription exists and is enabled.
- `check_resource_group`: Verifies the resource group exists in the subscription.
- `validate`: Uses an LLM to check provided fields against template parameters, types, and allowed values.
- `prompt_for_missing`: Interrupts and prompts the user for any missing or invalid parameters.

**Flow:**

```mermaid
flowchart TD
    START([START]) --> check_subscription
    check_subscription --> check_resource_group
    check_resource_group --> validate
    validate --> decision{parameters valid?}
    decision -- yes --> END([END])
    decision -- no --> prompt_for_missing
    prompt_for_missing --> END([END])
```

**Key Features:**

- LLM intelligently maps user fields to template parameters.
- Handles type checking, allowed values, and extra fields.
- Prompts user for missing/invalid parameters.

---

### 3. Deployment Subgraph (`agents/deployment_agent.py`)

**Purpose:**  
Deploys the validated ARM template to Azure, handling both resource group and subscription-level deployments.

**Nodes:**

- `resource_group_deployment`: Deploys to a resource group (creates it if needed).
- `subscription_deployment`: Deploys at the subscription scope.

**Flow:**

```mermaid
flowchart TD
    START([START]) --> decision{scope}
    decision -- resourceGroup --> resource_group_deployment
    decision -- subscription --> subscription_deployment
    resource_group_deployment --> END([END])
    subscription_deployment --> END([END])
```

**Key Features:**

- Uses Azure SDK for Python for deployments.
- Handles resource group creation if missing.
- Logs deployment status and errors.

---

### 4. Resource Action Agent (`agents/resource_action_agent.py`)

**Purpose:**  
Handles Azure resource management actions such as get, list, and delete for resources, using the Azure SDK.

**Nodes:**

- `get_resource`: Retrieves details of a specific Azure resource.
- `list_resources`: Lists resources of a specified type in a resource group.
- `delete_resource`: Deletes a specified Azure resource.

**Flow:**

```mermaid
flowchart TD
    START([START]) --> decision{intent}
    decision -- get --> get_resource
    decision -- list --> list_resources
    decision -- delete --> delete_resource
    get_resource --> END([END])
    list_resources --> END([END])
    delete_resource --> END([END])
```

**Key Features:**

- Uses Azure SDK for Python for all resource actions.
- Logs and stores all results in the workflow state in a consistent, JSON-formatted way.
- Handles missing required fields by interrupting and prompting for user input.
- Supports extensible intent-based routing for future resource actions.

---

## Main Graph Wiring (`graph.py`)

The **master graph** orchestrates the full workflow by chaining the subgraphs:

```mermaid
flowchart TD
    START([START]) --> intent_detection
    intent_detection --> decision{intent}
    decision -- get/list/delete --> resource_action
    decision -- create/update --> template_validation
    decision -- other --> END([END])
    resource_action --> END([END])
    template_validation --> deployment
    deployment --> END([END])
```

- Each subgraph is compiled and added as a node.
- State is passed between subgraphs, with all messages and progress logged.
- Interrupts (e.g., missing fields) are handled gracefully, prompting the user as needed.

---

## Message Logging & UI Integration

- **All user, agent, and system/progress messages are appended to the `messages` list in the state.**
- The UI (e.g., `streamlit_app.py`) displays the full conversation, including agent/system progress and interruptions.
- The Streamlit app formats and displays all messages, updating in real time as the workflow progresses.

**Example UI flow:**

1. User submits a request (e.g., "create a storage account...").
2. Each agent/subgraph appends progress/system messages (e.g., "Extracting intent...", "Validating template...").
3. If user input is needed, the system interrupts and prompts for missing fields.
4. All messages are shown in the chat interface, providing full transparency.

---

## ARM Template Storage

- ARM templates are stored in the `quickstarts/` directory, organized by resource type (e.g., `quickstarts/microsoft.storage/storageaccounts.json`).
- The intent detection agent dynamically loads the correct template based on the extracted resource type.

---

## How to Run

1. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

2. **Set up environment variables:**
   - `AZURE_OPENAI_API_KEY`
   - `AZURE_OPENAI_ENDPOINT`
   - `LLM_PROVIDER` (e.g., `openai` or `azure`)
   - `AZURE_CLIENT_ID`
   - `AZURE_CLIENT_SECRET`
   - `AZURE_TENANT_ID`
   - (Optional) `TEMPLATE_VECTORSTORE_PATH`

3. **Run the Streamlit app:**
   ```
   python streamlit_app.py
   ```

4. **Interact with the assistant:**
   - Enter natural language requests (e.g., "create a storage account named test in rg demo").
   - The UI will display all agent/system progress and prompt for any missing information.

---

## Extending the System

- **Add new resource types:**  
  Add new ARM templates to the `quickstarts/` directory.
- **Add new agents/subgraphs:**  
  Create new agent modules in `agents/` and wire them into the master graph.
- **Customize validation or deployment logic:**  
  Edit the relevant agent node functions for custom business logic or additional checks.

---

## File Structure

```
.
├── agents/
│   ├── intent_detection_langgraph.py
│   ├── template_validation_agent.py
│   ├── deployment_agent.py
│   └── resource_action_agent.py
├── quickstarts/
│   ├── microsoft.storage/
│   │   └── storageaccounts.json
│   └── microsoft.keyvault/
│       └── vaults.json
├── state_schemas.py
├── graph.py
├── streamlit_app.py
├── utils.py
├── requirements.txt
└── ...
```

---

## Appendix: Example Conversation Flow

**User:**  
`create a storage account with the following values, name: aiteststorg01, rg: myrg, subscription: 00000000-0000-0000-0000-000000000000 and region eastus`

**System/Agent Progress (as shown in UI):**
```
[System] Extracting intent...
[Agent] Intent: create, Resource Type: Microsoft.Storage/storageAccounts, Provided Fields: {...}
[System] Checking required scope fields...
[System] Loading ARM template for Microsoft.Storage/storageAccounts...
[System] Determining deployment scope...
[System] Validating template parameters...
[Agent] All required parameters are present and valid.
[System] Deploying to Azure...
[Agent] Deployment succeeded!
```

**If missing fields:**
```
[System] Please provide the following required fields: resource_group_name.
```

**All of the above messages are logged in the `messages` list and displayed in the UI.**

---

## Work In Progress (WIP)

### 1. Loading Templates from a Vector Store

Currently, ARM templates are loaded from the local file system based on the extracted `resource_type` (e.g., `quickstarts/microsoft.storage/storageaccounts.json`).

**Planned Improvement:**
- Store ARM templates in a vector store (e.g., FAISS, ChromaDB) with metadata including resource type, description, and tags.
- On intent extraction, use the resource type to query the vector store for the most relevant template, enabling fuzzy matching, semantic search, and easier extensibility.
- This will allow for more flexible template retrieval, support for similar resource types, and easier management of a large template library.

**Intended Approach:**
- Index all templates in the vector store at startup or via a management script.
- On user request, extract the resource type and use it as a query to the vector store.
- Retrieve the best-matching template and load it into the workflow state for validation and deployment.

### 2. Proper Logging

Currently, logging is handled via Python's built-in logging module and messages are appended to the in-memory state for UI display.

**Planned Improvement:**
- Implement structured logging (e.g., JSON logs) for all agent and system actions.
- Support persistent logging to disk, cloud storage, or external logging services (e.g., Azure Monitor, ELK, Datadog).
- Include correlation IDs, timestamps, and workflow/graph context in all logs for traceability.
- Optionally, expose logs via an API or UI for audit and debugging purposes.

---