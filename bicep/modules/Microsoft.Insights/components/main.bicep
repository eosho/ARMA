@description('Name of the Application Insights component')
param appInsightsName string

@description('Location for the Application Insights component')
param location string = resourceGroup().location

@description('Application type')
@allowed([
  'web'
  'other'
])
param applicationType string = 'web'

@description('Type of application insights resource')
@allowed([
  'web'
  'ios'
  'other'
  'store'
  'java'
  'phone'
])
param kind string = 'web'

@description('Retention in days')
@minValue(30)
@maxValue(730)
param retentionInDays int = 90

@description('Sampling percentage')
@minValue(0)
@maxValue(100)
param samplingPercentage int = 100

@description('Disable IP masking')
param disableIpMasking bool = false

@description('Log Analytics workspace ID')
param workspaceResourceId string = ''

@description('Tags for the Application Insights component')
param tags object = {}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: kind
  tags: tags
  properties: {
    Application_Type: applicationType
    RetentionInDays: retentionInDays
    SamplingPercentage: samplingPercentage
    DisableIpMasking: disableIpMasking
    WorkspaceResourceId: empty(workspaceResourceId) ? null : workspaceResourceId
    IngestionMode: empty(workspaceResourceId) ? 'ApplicationInsights' : 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
output instrumentationKey string = appInsights.properties.InstrumentationKey
output connectionString string = appInsights.properties.ConnectionString
