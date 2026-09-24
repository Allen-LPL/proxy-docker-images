#!/bin/sh
# Render an Xray config from the baked-in role template and environment
# variables, self-test it, then exec xray. Shared by every role image.
#
# Contract:
#   /etc/xray/template.json   role template with ${VAR} placeholders
#   /etc/xray/required.vars   one required variable name per line (# comments ok)
#   /etc/xray/config.json     render target (also the escape-hatch mount point)
#
# SELFTEST=1  render + `xray run -test` only, then exit 0 (used by build smoke).
set -eu

TEMPLATE=/etc/xray/template.json
REQUIRED=/etc/xray/required.vars
CONFIG=/etc/xray/config.json

if [ -f "$CONFIG" ]; then
    # Escape hatch: an externally mounted config wins over template rendering.
    echo "entrypoint: using mounted $CONFIG (skipping template render)"
else
    missing=""
    allow=""
    while IFS= read -r name || [ -n "$name" ]; do
        case "$name" in ""|\#*) continue ;; esac
        eval "val=\${$name-}"
        [ -z "$val" ] && missing="$missing $name"
        allow="$allow \${$name}"
    done < "$REQUIRED"
    if [ -n "$missing" ]; then
        echo "entrypoint: missing required env vars:$missing" >&2
        exit 1
    fi
    # Restrict envsubst to the declared allowlist so a literal $ in the
    # template (should any appear) is never clobbered.
    envsubst "$allow" < "$TEMPLATE" > "$CONFIG"
fi

mkdir -p /var/log/v2ray

echo "entrypoint: validating $CONFIG"
xray run -test -config "$CONFIG"

if [ -n "${SELFTEST:-}" ]; then
    echo "entrypoint: selftest OK"
    exit 0
fi

echo "entrypoint: starting xray"
exec xray run -config "$CONFIG"
