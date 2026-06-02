# Deploy to Azure Container Apps with Azure Entra Authentication

This guide shows how to deploy the MCP SQL Server to Azure Container Apps with Azure Entra ID (Entra) authentication and Key Vault secret management.

## Architecture

```
Azure Entra ID (Token Issuer)
         ↓
  Client App → MCP (ACA) ← Azure Key Vault (Secrets)
                  ↓
         SQL Server 2019 (Dual Instance)
```

## Prerequisites

- Azure subscription with Contributor role
- Azure CLI 2.50+
- Docker CLI (or use ACR build)
- An Entra ID tenant

## Step 1: Create Azure Resources

### 1a. Set Variables

```powershell
# Azure & Resource Group
$AZ_SUBSCRIPTION="<subscription-id>"
$AZ_LOCATION="eastus"
$AZ_RG="rg-mcp-sql"
$AZ_ACR="acrmcpsql$(Get-Random -Minimum 1000 -Maximum 9999)"
$AZ_ENV="cae-mcp-sql"
$AZ_APP="ca-mcp-sql"
$AZ_KEYVAULT="kv-mcp-sql-$(Get-Random -Minimum 1000 -Maximum 9999)"

# Entra (from app registration)
$ENTRA_TENANT_ID="<your-tenant-id>"
$ENTRA_CLIENT_ID="<your-app-client-id>"
$ENTRA_CLIENT_SECRET="<your-app-client-secret>"
$ENTRA_IDENTIFIER_URI="api://mcp-sql-server"

# SQL Credentials
$SQL_PRIMARY_USER="sa"
$SQL_PRIMARY_PASSWORD="<strong-password>"
$SQL_SECONDARY_USER="sa"
$SQL_SECONDARY_PASSWORD="<strong-password>"
```

### 1b. Login and Create Resources

```powershell
# Login
az login
az account set --subscription $AZ_SUBSCRIPTION

# Create resource group
az group create --name $AZ_RG --location $AZ_LOCATION

# Create ACR
az acr create --resource-group $AZ_RG --name $AZ_ACR --sku Basic

# Required for managed identity image pull from ACR
az acr config authentication-as-arm update -r $AZ_ACR --status enabled

# Create Key Vault
az keyvault create --name $AZ_KEYVAULT --resource-group $AZ_RG --location $AZ_LOCATION

# Store SQL credentials in Key Vault
az keyvault secret set --vault-name $AZ_KEYVAULT --name "sql-primary-username" --value $SQL_PRIMARY_USER
az keyvault secret set --vault-name $AZ_KEYVAULT --name "sql-primary-password" --value $SQL_PRIMARY_PASSWORD
az keyvault secret set --vault-name $AZ_KEYVAULT --name "sql-secondary-username" --value $SQL_SECONDARY_USER
az keyvault secret set --vault-name $AZ_KEYVAULT --name "sql-secondary-password" --value $SQL_SECONDARY_PASSWORD
az keyvault secret set --vault-name $AZ_KEYVAULT --name "entra-client-secret" --value $ENTRA_CLIENT_SECRET
```

## Step 2: Register App in Entra ID

Use the Azure Portal or Azure CLI to create an app registration:

1. Go to **Azure Portal** → **Entra ID** → **App Registrations** → **+ New Registration**
   - Name: `mcp-sql-server`
   - Supported account types: `Single tenant`
   - Redirect URI (optional)

2. Copy the following from app overview:
   - **Application (client) ID** → set as `$ENTRA_CLIENT_ID`
   - **Directory (tenant) ID** → set as `$ENTRA_TENANT_ID`

3. Go to **Certificates & Secrets** → **+ New client secret**:
   - Copy the secret value → set as `$ENTRA_CLIENT_SECRET`

4. Go to **Expose an API**:
   - Click **Add a scope**
   - Application ID URI: `api://mcp-sql-server`
   - Scope name: `access`
   - Admin consent display name: `Access MCP SQL Server`

5. Go to **API Permissions** → **+ Add a permission**:
   - Select **My APIs** → **mcp-sql-server**
   - Add the `access` scope

## Step 3: Build and Push Image to ACR

```powershell
# From repo root
az acr build --registry $AZ_ACR --image "mcp-sql-server:latest" --file docker/Dockerfile .

# Get ACR login server
$ACR_LOGIN_SERVER="$(az acr show --resource-group $AZ_RG --name $AZ_ACR --query loginServer -o tsv)"
Write-Host "ACR Login Server: $ACR_LOGIN_SERVER"
```

## Step 4: Create Container Apps Environment

```powershell
# Create CAE (managed environment)
az containerapp env create `
  --name $AZ_ENV `
  --resource-group $AZ_RG `
  --location $AZ_LOCATION

# Store environment ID for later reference
$CAE_ID="$(az containerapp env show --name $AZ_ENV --resource-group $AZ_RG --query id -o tsv)"
Write-Host "Container Apps Environment ID: $CAE_ID"
```

## Step 5: Enable Entra Auth in Config

Edit `config/runtime-policy.yaml` and set the auth section:

```yaml
auth:
  auth_mode: disabled  # Keep for backward compat
  azure_auth_enabled: true  # ENABLE THIS
  azure_group_authorization_enabled: false  # Set to true if using group-based read/write access
  azure_tenant_id: "<your-tenant-id>"
  azure_client_id: "<your-app-client-id>"
  azure_client_secret_ref: "secret/entra/client-secret"  # Resolver will read SECRET_ENTRA_CLIENT_SECRET
  azure_required_scopes: ["api://mcp-sql-server/access"]
  azure_base_url: ""  # Leave empty to use default Azure login
  azure_identifier_uri: "api://mcp-sql-server"
  azure_group_claim_name: "groups"
  azure_read_groups: []  # Example: ["group-uuid-read"]
  azure_write_groups: []  # Example: ["group-uuid-write"]
  pool_max_connections: 10
  pool_max_keepalive_connections: 10
  pool_timeout_seconds: 10
```

## Step 6: Rebuild Image with Config

```powershell
# Rebuild image with updated config
az acr build --registry $AZ_ACR --image "mcp-sql-server:latest" --file docker/Dockerfile .
```

## Step 7: Create Container App with Managed Identity

```powershell
# Create user-assigned managed identity for Key Vault access
$IDENTITY_NAME="mcp-sql-server-identity"
az identity create --name $IDENTITY_NAME --resource-group $AZ_RG

# Get identity resource ID and principal ID
$IDENTITY_ID="$(az identity show --name $IDENTITY_NAME --resource-group $AZ_RG --query id -o tsv)"
$IDENTITY_PRINCIPAL_ID="$(az identity show --name $IDENTITY_NAME --resource-group $AZ_RG --query principalId -o tsv)"
$ACR_ID="$(az acr show --resource-group $AZ_RG --name $AZ_ACR --query id -o tsv)"
$KEYVAULT_ID="$(az keyvault show --name $AZ_KEYVAULT --resource-group $AZ_RG --query id -o tsv)"

# Grant Key Vault and ACR permissions to identity (RBAC)
az role assignment create --assignee-object-id $IDENTITY_PRINCIPAL_ID --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope $KEYVAULT_ID
az role assignment create --assignee-object-id $IDENTITY_PRINCIPAL_ID --assignee-principal-type ServicePrincipal --role "AcrPull" --scope $ACR_ID

# Create the Container App
az containerapp create `
  --name $AZ_APP `
  --resource-group $AZ_RG `
  --environment $AZ_ENV `
  --image "$ACR_LOGIN_SERVER/mcp-sql-server:latest" `
  --target-port 8080 `
  --ingress external `
  --cpu 1.0 `
  --memory 2.0Gi `
  --registry-server $ACR_LOGIN_SERVER `
   --registry-identity $IDENTITY_ID `
   --user-assigned $IDENTITY_ID `
   --secrets `
      sqlpriuser=keyvaultref:https://$AZ_KEYVAULT.vault.azure.net/secrets/sql-primary-username,identityref:$IDENTITY_ID `
      sqlpripass=keyvaultref:https://$AZ_KEYVAULT.vault.azure.net/secrets/sql-primary-password,identityref:$IDENTITY_ID `
      sqlsecuser=keyvaultref:https://$AZ_KEYVAULT.vault.azure.net/secrets/sql-secondary-username,identityref:$IDENTITY_ID `
      sqlsecpass=keyvaultref:https://$AZ_KEYVAULT.vault.azure.net/secrets/sql-secondary-password,identityref:$IDENTITY_ID `
      entraclisec=keyvaultref:https://$AZ_KEYVAULT.vault.azure.net/secrets/entra-client-secret,identityref:$IDENTITY_ID `
  --env-vars `
    FASTMCP_HOST=0.0.0.0 `
    FASTMCP_PORT=8080 `
    FASTMCP_RATE_LIMIT_BACKEND=local `
    FASTMCP_AZURE_AUTH_ENABLED=true `
    FASTMCP_AZURE_TENANT_ID=$ENTRA_TENANT_ID `
    FASTMCP_AZURE_CLIENT_ID=$ENTRA_CLIENT_ID `
    FASTMCP_AZURE_CLIENT_SECRET_REF="secret/entra/client-secret" `
    FASTMCP_AZURE_IDENTIFIER_URI=$ENTRA_IDENTIFIER_URI `
    FASTMCP_AZURE_REQUIRED_SCOPES="api://mcp-sql-server/access" `
    FASTMCP_AZURE_GROUP_AUTHORIZATION_ENABLED=false `
   SECRET_SQL_PRIMARY_USERNAME=secretref:sqlpriuser `
   SECRET_SQL_PRIMARY_PASSWORD=secretref:sqlpripass `
   SECRET_SQL_SECONDARY_USERNAME=secretref:sqlsecuser `
   SECRET_SQL_SECONDARY_PASSWORD=secretref:sqlsecpass `
   SECRET_ENTRA_CLIENT_SECRET=secretref:entraclisec
```

Notes:
- `--user-assigned` and `identityref:` should use the managed identity resource ID, not just identity name.
- Container Apps secret names are limited in length, so short secret keys are used and then mapped to the app's expected environment variable names.

## Step 8: Get App FQDN and Test

```powershell
# Get the FQDN
$APP_FQDN="$(az containerapp show --name $AZ_APP --resource-group $AZ_RG --query properties.configuration.ingress.fqdn -o tsv)"
Write-Host "App URL: https://$APP_FQDN"

# Test health endpoint (no auth required)
Invoke-WebRequest -Uri "https://$APP_FQDN/diagnostics/health" -Method Get

# Test security endpoint
Invoke-WebRequest -Uri "https://$APP_FQDN/diagnostics/security" -Method Get

# Test MCP endpoint with Entra token (initialize + session flow)
$TOKEN = (az account get-access-token --scope "api://mcp-sql-server/access" --query accessToken -o tsv)

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$initHeaders = @{
   Authorization = "Bearer $TOKEN"
   Accept = "application/json, text/event-stream"
   "Content-Type" = "application/json"
}

$initBody = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"aca-smoke","version":"1.0"}}}'
$init = Invoke-WebRequest -Uri "https://$APP_FQDN/mcp/" -Method Post -Headers $initHeaders -Body $initBody -WebSession $session
$sid = $init.Headers['Mcp-Session-Id']

$callHeaders = @{
   Authorization = "Bearer $TOKEN"
   Accept = "application/json, text/event-stream"
   "Content-Type" = "application/json"
   "Mcp-Session-Id" = $sid
}

$callBody = '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
Invoke-WebRequest -Uri "https://$APP_FQDN/mcp/" -Method Post -Headers $callHeaders -Body $callBody -WebSession $session
```

## Step 9: SQL Connectivity from ACA

Your SQL servers need to be reachable from the Container App. Choose one approach:

### Option A: Public SQL (Not Recommended)
- SQL servers have public IPs/endpoints
- No firewall rules needed
- High security risk

### Option B: SQL in Azure VNet (Recommended)
1. Create a VNet with subnets for SQL and ACA
2. Create Container Apps Environment with VNet integration
3. Configure SQL firewall to allow traffic from ACA subnet

### Option C: Hybrid: SQL on-premises
- Set up Azure ExpressRoute or VPN Gateway
- Route traffic through hybrid connection
- Configure firewall allowlist

## Step 10: Monitor and Debug

```powershell
# View container logs
az containerapp logs show --name $AZ_APP --resource-group $AZ_RG --follow

# View container app details
az containerapp show --name $AZ_APP --resource-group $AZ_RG

# Check managed identity permissions
az role assignment list --assignee-object-id $IDENTITY_PRINCIPAL_ID --scope $KEYVAULT_ID -o table
az role assignment list --assignee-object-id $IDENTITY_PRINCIPAL_ID --scope $ACR_ID -o table
```

## Entra Auth Flow

When `azure_auth_enabled=true`:

1. Client sends HTTP request with `Authorization: Bearer <token>`
2. MCP verifies token signature against Azure JWKS
3. MCP extracts tenant, client_id, scopes from token claims
4. MCP checks required scopes match `azure_required_scopes`
5. If `azure_group_authorization_enabled=true`, MCP maps token groups to read/write privileges
6. Request proceeds with actor identity set from token `preferred_username` or `oid`

## Testing Entra Auth

### Get a token for testing:

```powershell
# Using CLI (requires you to authenticate to Entra first)
$TOKEN = (az account get-access-token --scope "api://mcp-sql-server/access" --query accessToken -o tsv)

# Or use Python to acquire token programmatically
python -c "
import msal
app = msal.PublicClientApplication(client_id='$ENTRA_CLIENT_ID', authority='https://login.microsoftonline.com/$ENTRA_TENANT_ID')
token = app.acquire_token_interactive(scopes=['api://mcp-sql-server/access'])
print(token['access_token'])
"
```

### Call MCP tools with token:

```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$headers = @{
   Authorization = "Bearer $TOKEN"
   Accept = "application/json, text/event-stream"
   "Content-Type" = "application/json"
}

$initBody = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"aca-smoke","version":"1.0"}}}'
$init = Invoke-WebRequest -Uri "https://$APP_FQDN/mcp/" -Method Post -Headers $headers -Body $initBody -WebSession $session
$sid = $init.Headers['Mcp-Session-Id']

$callHeaders = @{
   Authorization = "Bearer $TOKEN"
   Accept = "application/json, text/event-stream"
   "Content-Type" = "application/json"
   "Mcp-Session-Id" = $sid
}

$callBody = '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
Invoke-WebRequest -Uri "https://$APP_FQDN/mcp/" -Method Post -Headers $callHeaders -Body $callBody -WebSession $session
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `AzureAuthNotConfigured` | Set `FASTMCP_AZURE_AUTH_ENABLED=true` and other auth env vars |
| `InvalidTokenError: Bad token` | Token issuer doesn't match tenant; check `FASTMCP_AZURE_TENANT_ID` |
| `MissingRequiredScope` | Token doesn't include required scopes; add `api://mcp-sql-server/access` to app's API permissions |
| `KeyVaultAccessDenied` | Managed identity doesn't have permissions; verify `Key Vault Secrets User` role assignment on Key Vault |
| `ImagePullBackOff` | Ensure ACR has ARM token auth enabled and identity has `AcrPull` on ACR |
| `SQL connection timeout` | SQL server not reachable from ACA; check VNet routing, NSG rules, SQL firewall |
| Token validation hangs | Check HTTP client timeouts; default is 10 seconds in `FASTMCP_POOL_TIMEOUT_SECONDS` |

## Scaling & High Availability

For production:

1. **Horizontal Scale**: Add replicas (auto-scale based on CPU/memory)
   ```powershell
   az containerapp update --name $AZ_APP --resource-group $AZ_RG --scale-rule-name cpu-scale --scale-rule-type cpu-utilization --scale-rule-metadata percentage=70
   ```

2. **Rate Limiting**: Use Redis-backed rate limiting for multi-replica scenarios
   ```powershell
   # Create Redis
   az redis create --name mcp-redis --resource-group $AZ_RG --location $AZ_LOCATION --sku Basic --capacity 0
   
   # Update app to use Redis
   az containerapp update --name $AZ_APP --resource-group $AZ_RG `
     --set-env-vars FASTMCP_RATE_LIMIT_BACKEND=redis FASTMCP_REDIS_URL="<redis-connection-string>"
   ```

3. **Managed Identity for SQL**: Use Entra auth for SQL connections instead of stored secrets (future enhancement)

## Cleanup

```powershell
# Delete everything
az group delete --name $AZ_RG --yes --no-wait
```

## References

- [Azure Container Apps documentation](https://learn.microsoft.com/en-us/azure/container-apps/)
- [FastMCP authentication guide](https://gofastmcp.com/integrations/azure)
- [Azure Entra OIDC discovery](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-protocols-oidc)
