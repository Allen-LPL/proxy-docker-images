# proxy-docker-images

**Language:** English · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

Parameterized, reusable Docker images for an Xray-based proxy service chain.
One digest-pinned Xray core is wrapped per role; each node is brought up by
filling a short `.env` and running `docker compose up`. **No secrets ever live
in an image layer or in this repository.**

## What's in the box

Five roles, one image each (published to your own registry, e.g.
`<youruser>/infra:<role>`):

| role | what it is |
|---|---|
| `client-legacy` | old client — single global VMess exit, no split routing |
| `client` | new client — AI traffic over a double-layer REALITY chain, other traffic over the default exit |
| `server-legacy` | old server — VMess inbound |
| `server-gate` | new server, gate — REALITY gate behind an nginx SNI splitter |
| `server-exit` | new server, exit — REALITY terminal inbound |

## How it works

The image is a thin wrapper: a multi-stage build copies the `xray` binary and
its `geoip.dat`/`geosite.dat` from a **digest-pinned** official Xray image, so
the binary is bit-identical to upstream. The image carries only a role template
(`docker/templates/<role>.json`), a required-variable list
(`docker/vars/<role>.vars`), and a shared `entrypoint.sh`.

At start the entrypoint:

1. checks every variable in the role's required list is set (missing → abort with a clear message);
2. renders the JSONC template with `envsubst`, restricted to an allowlist of exactly those variables;
3. runs `xray run -test` to validate the rendered config — a bad config aborts *before* the proxy starts;
4. `exec`s xray.

Set `SELFTEST=1` to run steps 1–3 and exit 0 (used by the build smoke test).
If you mount a full config at `/etc/xray/config.json`, the entrypoint uses it
verbatim and skips rendering (it still `run -test`s first) — an escape hatch for
edge cases.

## Quick start

**Image namespace.** The images aren't hardcoded to any registry. Two knobs, set
them to the same value (your registry namespace, e.g. `youruser/infra`):

- `REPO` — env var read by `scripts/build-images` when building/pushing.
- `IMAGE_REPO` — set in each node's `.env`; the compose files read it (default
  `youruser/infra`). This is what a node pulls at `docker compose up`.

### Build & publish (maintainer)

```sh
docker login -u <youruser>              # run yourself; keep the password out of logs
REPO=<youruser>/infra scripts/build-images          # build + smoke-test all roles
REPO=<youruser>/infra scripts/build-images --push   # then publish rolling + dated tags
```

Every role is smoke-tested with `xray run -test` (using throwaway secrets)
**before any push**, so a broken template never reaches the registry. Override
the base image with `XRAY_BASE=<ref>` (e.g. a locally-cached `ghcr.io` digest);
unset, it defaults to the mirror digest in `docker/Dockerfile`.

### Bring up a node (operator, three steps)

```sh
cd deploy/<role>/
cp ../../docker/env/<role>.env.example .env    # then fill in real values
# set IMAGE_REPO in .env to your namespace (e.g. youruser/infra)
docker compose up -d
```

`server-gate` runs two containers: the REALITY gate on `127.0.0.1:GATE_PORT`
and an nginx SNI splitter on `:443` that forwards the matching SNI to the gate
and sends everything else to a decoy upstream. See
[`deploy/README.md`](deploy/README.md) for the full operator guide and
[`docs/design.md`](docs/design.md) for the design rationale.

## Configuration reference

Each role's variables are documented in `docker/env/<role>.env.example` —
including `IMAGE_REPO`. Copy it to `.env`, fill every `REPLACE_ME`, and keep the
result **out of git** (`.env` is gitignored). Generate a REALITY keypair with:

```sh
docker run --rm --entrypoint xray youruser/infra:server-exit x25519
```

## Security & caveats

- **This repository is public.** Never commit real endpoints, camouflage
  serverNames, UUIDs, or keys. The tracked `*.env.example` files are
  placeholders only; images contain no secrets.
- **Store filled `.env` files outside this repo** — a secrets manager or an
  encrypted store. They are gitignored so an accidental `git add` is caught.
- **`server-gate` / `server-exit` templates were rebuilt from a live topology.**
  `xray run -test` proves structural validity, not semantic parity — verify each
  field against your running gate/exit config before a production cutover.
- **Pin the nginx image to a digest** in `deploy/server-gate/docker-compose.yml`
  after the first pull; a version tag is used only to avoid `:latest`.
- The `REALITY: Listening on non-443 ports` warning for the gate/exit inbounds is
  expected — nginx fronts `:443` and forwards to the gate on loopback.
