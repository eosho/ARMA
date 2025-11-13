# Bicep Template Organization

## Directory Structure

Templates are organized by Azure resource type for automatic discovery:

```
bicep/modules/
├── Microsoft.Storage/
│   └── storageAccounts/
│       └── main.bicep
├── Microsoft.Compute/
│   └── virtualMachines/
│       └── main.bicep
├── Microsoft.Web/
│   └── sites/
│       └── main.bicep
├── Microsoft.Network/
│   └── virtualNetworks/
│       └── main.bicep
└── ...
```

## How It Works

1. **User Request**: "Deploy a storage account in westus"
2. **Intent Detection**: Orchestrator detects resource type: `Microsoft.Storage/storageAccounts`
3. **Template Discovery**: System looks for `bicep/modules/Microsoft.Storage/storageAccounts/main.bicep`
4. **Parameter Extraction**: Parses template to find required parameters
5. **Missing Parameter Detection**: Compares template requirements vs. state
6. **User Notification**: Tells user what parameters are missing

## Example Flow

```
User: "I want to deploy a storage account in westus"

System:
📋 Found template: main.bicep

Missing required parameters:
• storageAccountName (string): Name of the storage account

Details detected:
- Resource Type: Microsoft.Storage/storageAccounts
- Template: main.bicep
- Location: westus
- Resource Group: Not specified
- Subscription: Not specified

User: "Use mystorageacct001 as the storage account name"

System:
✓ Template discovered
✓ Parameters validated
✓ Proceeding to analysis...
```

## Adding New Templates

To add support for a new resource type:

1. Create directory matching the resource type:
   ```bash
   mkdir -p bicep/modules/Microsoft.KeyVault/vaults
   ```

2. Create `main.bicep` in that directory:
   ```bicep
   @description('Name of the key vault')
   param vaultName string

   @description('Location for the key vault')
   param location string = resourceGroup().location

   resource keyVault 'Microsoft.KeyVault/vaults@2023-02-01' = {
     name: vaultName
     location: location
     properties: {
       // ...
     }
   }
   ```

3. Update orchestrator prompt to recognize the resource type:
   - Edit `src/arma/agents/prompts/orchestrator.py`
   - Add mapping: `"key vault" → "Microsoft.KeyVault/vaults"`

That's it! The system will automatically discover and use the template.

## Benefits

- **No Code Changes**: Adding templates doesn't require code modifications
- **Self-Documenting**: Directory structure shows what's supported
- **Scalable**: Can support hundreds of resource types
- **Consistent**: All templates follow same pattern
- **Discoverable**: Easy to find templates by resource type
