#!/usr/bin/env bash
# Nearby Notices on Azure Container Apps, inside the free grant, with a budget alert and no registry cost.
#
# Run once, logged in as a service principal with Contributor on the resource group:
#   az login --service-principal -u $AZ_CLIENT_ID -p $AZ_CLIENT_SECRET --tenant $AZ_TENANT_ID
#   ./deploy/azure.sh
# Re-run safely: every step is create-or-update.
#
# Required environment:
#   GHCR_USER, GHCR_TOKEN      a GitHub token with read:packages, so Azure can pull the private image
#   NN_MODEL, NN_MODEL_API_BASE, NN_MODEL_API_KEY, NN_MODEL_API_VERSION   the model (an Azure OpenAI deployment, or any LiteLLM-named model)
#   ALERT_EMAIL                where the budget alert goes
set -euo pipefail

SUB="${AZ_SUBSCRIPTION_ID:-491578e0-a9b6-4165-a3b7-424a25b322d6}"
RG="${AZ_RESOURCE_GROUP:-nearby-notices}"
LOC="${AZ_LOCATION:-uksouth}"
ENV_NAME="nearby-notices-env"
APP="nearby-notices"
IMAGE="${IMAGE:-ghcr.io/OWNER/nearby-notices:latest}"

az account set --subscription "$SUB"
az group create -n "$RG" -l "$LOC" -o none

# 1. A budget alert before anything that can cost money: £5 a month, email at 80% and 100% of forecast and actual.
start=$(date -u +%Y-%m-01T00:00:00Z)
az config set extension.use_dynamic_install=yes_without_prompt -o none 2>/dev/null || true
az consumption budget create-with-rg --resource-group "$RG" --budget-name nearby-notices-monthly --amount 5 --category cost \
  --time-grain Monthly --time-period start-date="$start" end-date=2030-01-01T00:00:00Z \
  --notifications "{\"actual80\":{\"enabled\":true,\"operator\":\"GreaterThan\",\"threshold\":80,\"contactEmails\":[\"$ALERT_EMAIL\"]},\"actual100\":{\"enabled\":true,\"operator\":\"GreaterThan\",\"threshold\":100,\"contactEmails\":[\"$ALERT_EMAIL\"]}}" \
  -o none 2>/dev/null || echo "budget: already exists or the consumption extension is unavailable; set it in the portal (Cost Management > Budgets)"

# 2. The Container Apps environment (consumption plan; the monthly free grant covers a small public tool).
az containerapp env create -n "$ENV_NAME" -g "$RG" -l "$LOC" --logs-destination none -o none 2>/dev/null || true

# 2b. Persistent storage for the SQLite cache: a 5 GB Azure Files share mounted at /data, so a deploy or a scale-to-zero
#     does not empty the cache. SQLite cannot use WAL on a network share, so the app runs with NN_DB_JOURNAL=DELETE there.
#     (Microsoft.Storage must be registered on the subscription once, by an Owner: az provider register -n Microsoft.Storage)
SA="${STORAGE_ACCOUNT:-nearbynotices$(date +%s | tail -c 6)}"
az storage account show -n "$SA" -g "$RG" -o none 2>/dev/null || az storage account create -n "$SA" -g "$RG" -l "$LOC" --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false -o none
SA_KEY=$(az storage account keys list -n "$SA" -g "$RG" --query '[0].value' -o tsv)
az storage share-rm create --storage-account "$SA" -n data --quota 5 -o none 2>/dev/null || true
az containerapp env storage set -n "$ENV_NAME" -g "$RG" --storage-name data --azure-file-account-name "$SA" --azure-file-account-key "$SA_KEY" --azure-file-share-name data --access-mode ReadWrite -o none

# 3. The app: one replica at most, scale to zero when idle, the model settings and the registry token as secrets.
az containerapp create -n "$APP" -g "$RG" --environment "$ENV_NAME" --image "$IMAGE" \
  --registry-server ghcr.io --registry-username "$GHCR_USER" --registry-password "$GHCR_TOKEN" \
  --target-port 8765 --ingress external --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1.0Gi \
  --secrets model-key="$NN_MODEL_API_KEY" \
  --env-vars NN_MODEL="$NN_MODEL" NN_MODEL_API_BASE="$NN_MODEL_API_BASE" NN_MODEL_API_VERSION="${NN_MODEL_API_VERSION:-}" \
             NN_MODEL_API_KEY=secretref:model-key NN_DAILY_CALL_CAP="${NN_DAILY_CALL_CAP:-600}" NN_SEARCHES_PER_MINUTE=6 NN_DB_PATH=/data/notices.sqlite \
  -o none 2>/dev/null || \
az containerapp update -n "$APP" -g "$RG" --image "$IMAGE" \
  --set-env-vars NN_MODEL="$NN_MODEL" NN_MODEL_API_BASE="$NN_MODEL_API_BASE" NN_MODEL_API_VERSION="${NN_MODEL_API_VERSION:-}" \
                 NN_DAILY_CALL_CAP="${NN_DAILY_CALL_CAP:-600}" NN_SEARCHES_PER_MINUTE=6 NN_DB_PATH=/data/notices.sqlite -o none

echo "live at: https://$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
