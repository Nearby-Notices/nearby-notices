// Nearby Notices on Azure, declared as code: everything in the resource group the live service runs on.
// Check it against the live estate without changing anything:
//   az deployment group what-if -g nearby-notices -f infra/main.bicep -p @infra/params.json -p <secure values>
// Secrets (model key, counter table link, registry token) are secure parameters, never written here.
// deploy/azure.sh remains the imperative route; this file is the declaration the estate is checked against.

@description('Azure region for every resource.')
param location string = resourceGroup().location

@description('Container image to run, pinned by commit hash.')
param image string

@description('Registry user that can pull the private image.')
param registryUser string

@secure()
@description('Registry token with read:packages.')
param registryToken string

@secure()
@description('Azure OpenAI key, passed to the app as a secret.')
param modelKey string

@secure()
@description('Table-scoped SAS link for the daily search counters.')
param counterUrl string

@description('Where the budget alerts go.')
param alertEmail string

@description('First day of the budget period (YYYY-MM-01).')
param budgetStart string

var envName = 'nearby-notices-env'
var appName = 'nearby-notices'
var filesAccountName = 'nearbynotices85414'
var countersAccountName = 'nnnotices6ef4cf'
var domains = [
  { name: 'nearbynotices.co.uk', cert: 'mc-nearby-notices-nearbynotices-co-8935', validation: 'TXT' }
  { name: 'www.nearbynotices.co.uk', cert: 'mc-nearby-notices-www-nearbynotice-3896', validation: 'CNAME' }
]

// Storage: one account holds the SQLite cache share, the other the daily counters table. TLS 1.2, no public blobs.
resource filesAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: filesAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: filesAccount
  name: 'default'
  properties: {
    shareDeleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource dataShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: 'data'
  properties: { shareQuota: 5, accessTier: 'TransactionOptimized' }
}

resource countersAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: countersAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
}

resource tableService 'Microsoft.Storage/storageAccounts/tableServices@2023-05-01' = {
  parent: countersAccount
  name: 'default'
}

resource countersTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  parent: tableService
  name: 'counters'
}

// The model: Azure OpenAI with one deployment, capacity 250 (requests and thousand tokens a minute), pay per token.
resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'nearby-notices-ai'
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: 'nearby-notices-ai'
    publicNetworkAccess: 'Enabled'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'gpt-4.1-mini'
  sku: { name: 'GlobalStandard', capacity: 250 }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-4.1-mini', version: '2025-04-14' }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

// The Container Apps environment: consumption plan, the cache share mounted as storage, managed certificates.
resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    zoneRedundant: false
    workloadProfiles: [ { name: 'Consumption', workloadProfileType: 'Consumption' } ]
    peerAuthentication: { mtls: { enabled: false } }
    peerTrafficConfiguration: { encryption: { enabled: false } }
  }
}

resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: 'data'
  properties: {
    azureFile: {
      accountName: filesAccount.name
      accountKey: filesAccount.listKeys().keys[0].value
      shareName: dataShare.name
      accessMode: 'ReadWrite'
    }
  }
}

resource certs 'Microsoft.App/managedEnvironments/managedCertificates@2024-03-01' = [for d in domains: {
  parent: env
  name: d.cert
  location: location
  properties: {
    subjectName: d.name
    domainControlValidation: d.validation
  }
}]

// The app: one replica at most, scales to zero when idle, kept warm in working hours, secrets by reference only.
resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      maxInactiveRevisions: 100
      ingress: {
        external: true
        targetPort: 8765
        transport: 'Auto'
        allowInsecure: false
        traffic: [ { latestRevision: true, weight: 100 } ]
        customDomains: [for (d, i) in domains: {
          name: d.name
          certificateId: certs[i].id
          bindingType: 'SniEnabled'
        }]
      }
      registries: [ { server: 'ghcr.io', username: registryUser, passwordSecretRef: 'ghcrio-${toLower(registryUser)}' } ]
      secrets: [
        { name: 'ghcrio-${toLower(registryUser)}', value: registryToken }
        { name: 'model-key', value: modelKey }
        { name: 'counter-url', value: counterUrl }
      ]
    }
    template: {
      containers: [
        {
          name: appName
          image: image
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'NN_MODEL', value: 'azure/gpt-4.1-mini' }
            { name: 'NN_MODEL_API_BASE', value: openai.properties.endpoint }
            { name: 'NN_MODEL_API_VERSION', value: '2024-10-21' }
            { name: 'NN_MODEL_API_KEY', secretRef: 'model-key' }
            { name: 'NN_DAILY_CALL_CAP', value: '600' }
            { name: 'NN_SEARCHES_PER_MINUTE', value: '6' }
            { name: 'NN_DB_PATH', value: '/data/notices.sqlite' }
            { name: 'NN_DB_JOURNAL', value: 'DELETE' }
            { name: 'NN_COUNTER_URL', secretRef: 'counter-url' }
          ]
          volumeMounts: [ { volumeName: 'data', mountPath: '/data' } ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          { name: 'http', http: { metadata: { concurrentRequests: '10' } } }
          {
            name: 'weekday-hours'
            custom: {
              type: 'cron'
              metadata: { timezone: 'Europe/London', start: '0 8 * * 1-5', end: '0 18 * * 1-5', desiredReplicas: '1' }
            }
          }
        ]
      }
      volumes: [
        {
          name: 'data'
          storageType: 'AzureFile'
          storageName: envStorage.name
          mountOptions: 'nobrl,cache=none,dir_mode=0777,file_mode=0777,uid=0,gid=0'
        }
      ]
    }
  }
}

// Cost control before anything else: £5 a month, email at 80% and 100% of actual spend.
resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'nearby-notices-monthly'
  properties: {
    category: 'Cost'
    amount: 5
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStart, endDate: '2030-01-01T00:00:00Z' }
    notifications: {
      actual80: { enabled: true, operator: 'GreaterThan', threshold: 80, contactEmails: [ alertEmail ] }
      actual100: { enabled: true, operator: 'GreaterThan', threshold: 100, contactEmails: [ alertEmail ] }
    }
  }
}

output url string = 'https://${app.properties.configuration.ingress.fqdn}'
