# Azure Container Apps + Entra Auth Deployment Checklist

## Pre-Deployment

- [ ] Azure subscription with Contributor role access
- [ ] Azure CLI 2.50+ installed (`az version`)
- [ ] Docker CLI installed
- [ ] Git repo cloned locally
- [ ] PowerShell 7+ (for script examples)

## Phase 1: Entra Setup (5 minutes)

- [ ] Register app in Entra ID → copy Tenant ID, Client ID
- [ ] Create client secret → copy secret value
- [ ] Expose API: set Application ID URI to `api://mcp-sql-server`
- [ ] Add scope `access` to API
- [ ] Add API permission for the scope to the app

## Phase 2: Azure Resource Creation (10 minutes)

```powershell
# Set variables from Phase 1
$AZ_SUBSCRIPTION="<subscription-id>"
$AZ_LOCATION="eastus"
$AZ_RG="rg-mcp-sql"
$AZ_ACR="acrmcpsql$(Get-Random -Minimum 1000 -Maximum 9999)"
$AZ_ENV="cae-mcp-sql"
$AZ_APP="ca-mcp-sql"
$AZ_KEYVAULT="kv-mcp-sql-$(Get-Random -Minimum 1000 -Maximum 9999)"

$ENTRA_TENANT_ID="<your-tenant-id>"
$ENTRA_CLIENT_ID="<your-app-client-id>"
$ENTRA_CLIENT_SECRET="<your-app-client-secret>"

$SQL_PRIMARY_PASSWORD="<strong-password>"
$SQL_SECONDARY_PASSWORD="<strong-password>"
```

- [ ] Login: `az login` and set subscription
- [ ] Create resource group: `az group create ...`
- [ ] Create ACR: `az acr create ...`
- [ ] Create Key Vault: `az keyvault create ...`
- [ ] Store secrets in Key Vault:
  - [ ] `sql-primary-username`
  - [ ] `sql-primary-password`
  - [ ] `sql-secondary-username`
  - [ ] `sql-secondary-password`
  - [ ] `entra-client-secret`

## Phase 3: Build and Push Image (5 minutes)

- [ ] Review [docs/azure-container-apps-deployment.md](docs/azure-container-apps-deployment.md) Step 3
- [ ] Run: `az acr build --registry $AZ_ACR --image "mcp-sql-server:latest" --file docker/Dockerfile .`
- [ ] Verify image in ACR: `az acr repository show --name $AZ_ACR --repository mcp-sql-server`

## Phase 4: Enable Entra Auth in Config (5 minutes)

- [ ] Copy `config/runtime-policy-entra-example.yaml` → `config/runtime-policy.yaml`
- [ ] Replace placeholders:
  - [ ] `{{ ENTRA_TENANT_ID }}`
  - [ ] `{{ ENTRA_CLIENT_ID }}`
- [ ] Review auth settings, especially:
  - [ ] `azure_auth_enabled: true`
  - [ ] `azure_group_authorization_enabled: false` (or `true` if using group-based access)
  - [ ] `azure_required_scopes: ["api://mcp-sql-server/access"]`
- [ ] Commit and push (or just save for local testing)

## Phase 5: Rebuild Image with Config (5 minutes)

- [ ] Run: `az acr build --registry $AZ_ACR --image "mcp-sql-server:latest" --file docker/Dockerfile .`
- [ ] Verify new image pushed

## Phase 6: Create Container Apps Environment (3 minutes)

- [ ] Run: `az containerapp env create --name $AZ_ENV ...`
- [ ] Verify: `az containerapp env show --name $AZ_ENV --resource-group $AZ_RG`

## Phase 7: Create Managed Identity (3 minutes)

- [ ] Create identity: `az identity create --name mcp-sql-server-identity ...`
- [ ] Grant Key Vault access: `az keyvault set-policy ...`
- [ ] Verify permissions: `az keyvault get-policy ...`

## Phase 8: Deploy Container App (5 minutes)

- [ ] Run full `az containerapp create` command from [docs/azure-container-apps-deployment.md](docs/azure-container-apps-deployment.md) Step 7
- [ ] Wait for deployment to complete (~2 minutes)
- [ ] Verify app created: `az containerapp show --name $AZ_APP ...`

## Phase 9: Post-Deployment Validation (5 minutes)

- [ ] Get app FQDN: `az containerapp show ... --query properties.configuration.ingress.fqdn`
- [ ] Test health endpoint (no auth): `curl https://<fqdn>/diagnostics/health`
- [ ] Test security endpoint: `curl https://<fqdn>/diagnostics/security`
  - Should show: `azure_auth_enabled: true`
- [ ] Acquire Entra token: `$TOKEN = (az account get-access-token --scope "api://mcp-sql-server/access" --query accessToken -o tsv)`
- [ ] Test MCP endpoint with auth (JSON-RPC):
  ```powershell
  Invoke-WebRequest -Uri "https://<fqdn>/mcp" `
    -Method Post `
    -Headers @{Authorization="Bearer $TOKEN"} `
    -Body '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' `
    -ContentType "application/json"
  ```

## Phase 10: Test SQL Connectivity (Optional, varies by network setup)

- [ ] Update `config/instances.yaml` with your SQL Server IPs/FQDNs
- [ ] Rebuild image
- [ ] Verify `/diagnostics/pool` endpoint shows healthy connections for both instances

## Post-Deployment

- [ ] Monitor logs: `az containerapp logs show --name $AZ_APP ... --follow`
- [ ] Set up scaling (auto-scale rules)
- [ ] Configure Azure Monitor / Application Insights
- [ ] Set up alerts for failed health checks
- [ ] Document any network policies (VNet, NSG, SQL firewall rules)

## Rollback

If deployment fails:
- [ ] Check logs: `az containerapp logs show ...`
- [ ] Disable Entra auth: `azure_auth_enabled: false`
- [ ] Rebuild image and redeploy
- [ ] Verify health endpoint: `curl https://<fqdn>/diagnostics/health`

## Quick Reference: Environment Variables

All required env vars are set in Step 7 `az containerapp create`. Key ones:

| Env Var | Value | Source |
|---------|-------|--------|
| `FASTMCP_AZURE_AUTH_ENABLED` | `true` | Config toggle |
| `FASTMCP_AZURE_TENANT_ID` | From Phase 1 | Entra app |
| `FASTMCP_AZURE_CLIENT_ID` | From Phase 1 | Entra app |
| `FASTMCP_AZURE_CLIENT_SECRET_REF` | `secret/entra/client-secret` | Key Vault reference |
| `FASTMCP_AZURE_IDENTIFIER_URI` | `api://mcp-sql-server` | Entra Expose API |
| `FASTMCP_AZURE_REQUIRED_SCOPES` | `api://mcp-sql-server/access` | Entra scope |
| `SECRET_SQL_PRIMARY_PASSWORD` | `secretref:sqlpripass` | Container Apps secret mapped from Key Vault |
| `SECRET_SQL_SECONDARY_PASSWORD` | `secretref:sqlsecpass` | Container Apps secret mapped from Key Vault |
| `SECRET_ENTRA_CLIENT_SECRET` | `secretref:entraclisec` | Container Apps secret mapped from Key Vault |

## Troubleshooting

See [docs/azure-container-apps-deployment.md](docs/azure-container-apps-deployment.md) **Troubleshooting** section for common issues and fixes.

## Next Steps

1. **High Availability**: Add auto-scaling and Azure Front Door
2. **Logging**: Integrate Azure Monitor and Application Insights
3. **CI/CD**: Set up GitHub Actions to auto-build on push
4. **SQL Auth**: Migrate from passwords to Entra auth for SQL connections (future feature)
5. **Group-Based Access**: Enable `azure_group_authorization_enabled` and configure `azure_read_groups`/`azure_write_groups` for fine-grained access

## Estimated Total Time: ~45 minutes

Breakdown:
- Entra setup: 5 min
- Azure resources: 10 min
- Build/push: 5 min
- Config update: 5 min
- Container Apps deploy: 10 min
- Testing: 5 min
- Buffer: 5 min
