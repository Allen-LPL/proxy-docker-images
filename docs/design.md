# Design: proxy-chain Docker images

## Goal

Package an Xray-based proxy service chain into a set of reusable, parameterized
Docker images. Distinguish **old client, new client, old server, new server**
(the new server splits by a two-hop topology into a **gate** and an **exit**
role, so five tags total). An operator pulls an image, fills a short `.env`, and
starts the node — supporting both **disaster-recovery rebuilds** of an existing
node and **parameterized new nodes**.

## Non-goals (YAGNI)

- No credentials baked into image layers.
- No CI service; build/push is a single local script.
- Single architecture (`linux/amd64`).
- Does not change how any running node operates; this produces images and deploy
  artifacts only.

## Image set

One image per role, published to your own registry as `<repo>:<role>`, each with
an immutable `-YYYYMMDD` copy for rollback:

| tag | role | notes |
|---|---|---|
| `client-legacy` | old client | single global VMess exit, no split routing |
| `client` | new client | AI traffic → double-layer REALITY chain; other → default VMess exit |
| `server-legacy` | old server | VMess inbound; one image, different `.env` per endpoint |
| `server-gate` | new server, gate | REALITY gate + identity routing; nginx SNI splitter via compose |
| `server-exit` | new server, exit | REALITY terminal inbound; only accepts gate-forwarded traffic |

## Base image & build strategy

Multi-stage build: `COPY` the binary and geo data from a **digest-pinned**
official Xray image, so the binary is bit-identical to upstream (same digest =
same binary):

```dockerfile
ARG XRAY_BASE=<mirror>/xtls/xray-core@sha256:<digest>
ARG ROLE
FROM ${XRAY_BASE} AS core
FROM alpine:3.20
RUN apk add --no-cache gettext ca-certificates
COPY --from=core /usr/local/bin/xray /usr/local/bin/xray
COPY --from=core /usr/local/share/xray/ /usr/local/share/xray/   # geoip.dat / geosite.dat
COPY entrypoint.sh /entrypoint.sh
COPY templates/${ROLE}.json /etc/xray/template.json
COPY vars/${ROLE}.vars /etc/xray/required.vars
```

- `XRAY_BASE` defaults to a mirror digest reference; override with
  `--build-arg XRAY_BASE=ghcr.io/...` (or `XRAY_BASE=` env for `build-images`)
  when the build host can reach the official registry directly.
- `ROLE` selects which template and required-vars list are baked in. One
  Dockerfile + one entrypoint cover all five roles.
- `docker login` is run by the operator interactively; credentials never enter
  logs.

## Config injection: the entrypoint contract

The image carries no credentials. Each role has a JSONC template (`${VAR}`
placeholders) plus a required-variable list `vars/<role>.vars` (one name per
line). Startup:

```
1. Read /etc/xray/required.vars; abort (exit 1) listing any empty variables.
2. Escape hatch: if /etc/xray/config.json is mounted, use it and skip rendering.
3. Otherwise envsubst renders template.json -> config.json, restricted to the
   required.vars allowlist (so a literal $ in the template is never clobbered).
4. xray run -test -config /etc/xray/config.json — invalid config aborts here.
5. exec xray run -config /etc/xray/config.json
```

The container runs as `--user 0` to read a `0600` mounted config; `run -test`
needs a writable `/var/log/v2ray` (created by the entrypoint).

## Per-node config archive (disaster recovery)

Each node's filled `.env` is kept in your own secret store (a secrets manager,
or an encrypted file via `ansible-vault` / `sops` / `age`) — **never committed**.

- Rebuild = pull image + restore that node's `.env` + `docker compose up`.
- Credentials never hit plaintext; template, image, and encrypted `.env` are
  three separate places — no single one is enough to reconstruct a usable chain.

## Gate compose orchestration

`deploy/server-gate/docker-compose.yml`:

- `xray` service: this repo's `server-gate` image, REALITY gate on
  `127.0.0.1:GATE_PORT`; the allowed identity is routed only to the exit, else
  blocked.
- `nginx` service: digest-pinned official image, stream-level SNI split — the
  camouflage serverName goes to xray, probes go to a decoy upstream. The nginx
  config is also `.env` + `envsubst` rendered.
- Two containers upgrade independently, matching a real nginx-stream-front +
  REALITY-backend topology.

## Build / push / verify

`scripts/build-images`:

1. `docker build --build-arg ROLE=<role>` per tag.
2. Render with throwaway secrets and run `xray run -test` — **prove the image
   starts before any push**.
3. Only when all green, `docker push <repo>:<tag>` and `:<tag>-YYYYMMDD`.

`tests/` asserts the Dockerfile pins its base by digest, the entrypoint gates on
`run -test` before exec, and nothing uses `:latest`.

## Risks & verification

- **Server template semantic parity:** `server-gate` / `server-exit` templates
  are rebuilt from a documented live structure. `run -test` proves structure,
  not semantic parity — verify field-by-field against the running configs before
  a production cutover.
- **Does not touch running services:** this produces images and deploy artifacts
  only; replacing a live container is a separate decision.
- **Credential boundary:** templates and images never contain plaintext
  credentials; `.env.example` uses placeholders; real values live only in the
  secret store and on the running node.
