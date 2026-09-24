# Operator guide

Bring up a proxy node from a published image in three steps. Secrets never live
in the image; you supply them at deploy time via `.env`.

| role | tag |
|---|---|
| old client — single global VMess exit | `client-legacy` |
| new client — AI over double-layer REALITY, other over default | `client` |
| old server — VMess inbound | `server-legacy` |
| new server, gate — REALITY + nginx SNI splitter | `server-gate` |
| new server, exit — REALITY terminal | `server-exit` |

## Build & publish (maintainer)

```sh
docker login -u <youruser>          # run yourself; password stays out of logs
REPO=<youruser>/infra scripts/build-images          # build + smoke test all roles
REPO=<youruser>/infra scripts/build-images --push   # then publish rolling + dated tags
```

Every role is smoke-tested (`xray run -test`) with throwaway secrets before any
push, so a broken template never reaches the registry.

## Bring up a node (three steps)

```sh
cd deploy/<role>/
cp ../../docker/env/<role>.env.example .env    # then fill in real values
docker compose up -d
```

The container renders `.env` into the config, runs `xray run -test`, and only
starts if the config is valid. A missing variable aborts with a clear message.

### Where real values come from

- **New node:** copy the role's `.env.example`, fill every `REPLACE_ME` from
  your own records, and bring the node up. Generate a REALITY keypair with:
  ```sh
  docker run --rm --entrypoint xray <youruser>/infra:server-exit x25519
  ```
- **Disaster recovery (rebuild an existing node):** restore that node's saved
  `.env` from your secret store and drop it in as `deploy/<role>/.env`.

Keep every filled `.env` **out of git** (they are gitignored) and in a proper
secret store — a secrets manager, or an encrypted file (e.g. `ansible-vault`,
`sops`, `age`). The image never contains these values.

## Escape hatch

If you mount a full config at `/etc/xray/config.json`, the entrypoint uses it
verbatim and skips template rendering (it still runs `xray run -test` first).

## Notes

- `server-gate` runs two containers (see its `docker-compose.yml`): the REALITY
  gate on `127.0.0.1:GATE_PORT` and an nginx SNI splitter on `:443`. Pin the
  nginx image to a digest after the first pull.
- `server-gate` / `server-exit` templates were rebuilt from a documented live
  structure. Verify field-by-field against your running gate/exit configs before
  a production cutover — `run -test` proves structure, not semantic parity.
