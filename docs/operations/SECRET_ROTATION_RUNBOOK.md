# Secret Rotation Runbook

This repository no longer stores local `.env` files or bundled certificate/key material.

## Rotate immediately

- Database credentials referenced by `DATABASE_URL`
- `SETTINGS_VAULT_KEY`
- `JWT_SECRET`
- `PHOTOGRAMMETRY_ASSET_SIGNING_SECRET`
- MQTT CA/server certificates and private keys
- OPC UA certificate and private key
- Raspberry Pi SSH credentials and passwords
- Any third-party API tokens previously kept in local `.env` files

## Minimum rotation procedure

1. Generate new values outside the repository using your secret manager or platform tooling.
2. Update the runtime secret store used by each environment.
3. Redeploy the API, worker, and frontend environments with the new values.
4. Invalidate old credentials where the provider supports revocation.
5. Confirm application startup, login, telemetry, and photogrammetry flows still work.
6. Review CI and deployment logs for startup failures caused by missing secrets.

## Storage standard going forward

- Commit only `.env.example` files with placeholders.
- Mount certificates and SSH keys from a secret store or deploy-time volume.
- Keep production secrets in the platform secret manager, not in `docker-compose.yml`.
- Treat any future secret-scan failure in CI as a release blocker.
