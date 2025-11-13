targetScope = 'subscription'

@description('Location for the resource group')
param location string

@description('Name of the resource group')
param resourceGroupName string

@description('Tags for the resource group')
param tags object = {}

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

output resourceGroupId string = rg.id
output resourceGroupName string = rg.name
