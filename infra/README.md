# Infrastructure as code

**Created:** 23/10/2026-05:53 (BST)  *(2026-10-23T04:53Z)*
**Last updated:** 23/10/2026-05:53 (BST)  *(2026-10-23T04:53Z)*

`main.bicep` declares everything in the resource group the live service runs on: both storage accounts (the cache share and the counters table), the Azure OpenAI account and its gpt-4.1-mini deployment (capacity 250), the Container Apps environment with its file storage and two managed certificates, the app itself (scale rules, custom domains, secrets by reference, the mounted cache), and the £5 monthly budget with its alerts. Secrets are secure parameters and never appear in the file.

## Checking it against the live estate

```
az deployment group what-if -g nearby-notices -f infra/main.bicep \
  -p image=<running image> registryUser=<user> registryToken=<token> modelKey=<key> counterUrl=<sas> \
     alertEmail=<email> budgetStart=2026-10-01T00:00:00Z
```

What-if changes nothing; it reports how the live estate differs from the declaration. On 23 October 2026 it reported **no change** on 10 of 14 resources. The other 4 differ only on properties Azure sets at run time or reports read-only (the app's running status and exposed port, the deployment's current capacity, the certificates' validation method as reported back), plus the model endpoint, which what-if shows as an unresolved reference to the same account.

CI compiles and lints the template on every push. `deploy/azure.sh` remains the imperative route that created the estate; this file is the declaration it is checked against.
