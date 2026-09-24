# Thin, parameterized wrapper around a digest-pinned Xray core.
#
# The xray binary is COPYed from the same digest that runs on every managed
# VM, HK and MS host, so it is bit-identical to production. The final image
# carries only a role template + required-vars list + entrypoint; no secrets.
#
#   docker build --build-arg ROLE=<role> -t youruser/infra:<role> docker/
#
# Roles: client-legacy client server-legacy server-exit server-gate

# Default base is the NJU ghcr mirror digest (reachable from CN, byte-identical
# to the official image). Override with --build-arg XRAY_BASE=ghcr.io/... if
# your build host can reach ghcr.io directly.
ARG XRAY_BASE=ghcr.nju.edu.cn/xtls/xray-core@sha256:c98160906f3fe1d9d16e950c2a7997dc0c542c71816aa92c21e510412f90e1a2

FROM ${XRAY_BASE} AS core

FROM alpine:3.20
ARG ROLE
RUN apk add --no-cache gettext ca-certificates \
    && mkdir -p /var/log/v2ray /etc/xray
COPY --from=core /usr/local/bin/xray /usr/local/bin/xray
# geoip.dat / geosite.dat back the geoip:/geosite: routing rules.
COPY --from=core /usr/local/share/xray/ /usr/local/share/xray/
ENV XRAY_LOCATION_ASSET=/usr/local/share/xray
COPY entrypoint.sh /entrypoint.sh
COPY templates/${ROLE}.json /etc/xray/template.json
COPY vars/${ROLE}.vars /etc/xray/required.vars
RUN chmod 755 /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
