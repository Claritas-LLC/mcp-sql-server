# Run MCP Server with Docker

## Files

- `.env.example` -> copy to `.env`
- `config/instances.runtime.example.yaml` -> copy values into `config/instances.yaml`
- `docker/docker-compose.runtime.yml` -> runtime compose file

## Steps

1. Copy `.env.example` to `.env` and set SQL credentials.
2. Update `config/instances.yaml` using `config/instances.runtime.example.yaml` as the template.
3. Start the server:

```powershell
docker compose -f docker/docker-compose.runtime.yml up -d
```

4. Optional Redis-backed rate limiting:

```powershell
docker compose -f docker/docker-compose.runtime.yml --profile local-redis up -d
```

5. Verify:

- `http://localhost:8085/`
- `http://localhost:8085/diagnostics/health`
- `http://localhost:8085/diagnostics/security`

## Important Notes

- The container listens on port `8080`; host port is mapped to `8085`.
- Use `host.docker.internal` instead of `localhost` when the SQL Server runs on the Docker host.
- Credential env vars must match the `auth_secret_ref` names in `config/instances.yaml`.
