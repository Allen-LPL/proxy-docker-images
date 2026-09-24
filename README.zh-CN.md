# proxy-docker-images

**语言:** [English](README.md) · 简体中文 · [日本語](README.ja.md)

为基于 Xray 的代理服务链提供参数化、可复用的 Docker 镜像。一个按摘要锁定(digest-pinned)的 Xray 核心按角色封装成镜像;每个节点只需填写一份简短的 `.env` 并运行 `docker compose up` 即可拉起。**任何密钥都不会进入镜像层,也不会出现在本仓库中。**

## 镜像里有什么

五个角色,每个角色一个镜像(发布到你自己的 registry,例如 `<youruser>/infra:<role>`):

| 角色 | 说明 |
|---|---|
| `client-legacy` | 旧客户端 —— 单一全局 VMess 出口,无分流路由 |
| `client` | 新客户端 —— AI 流量走双层 REALITY 链路,其余流量走默认出口 |
| `server-legacy` | 旧服务端 —— VMess 入站 |
| `server-gate` | 新服务端 · 网关(gate) —— REALITY 网关,前置 nginx SNI 分流器 |
| `server-exit` | 新服务端 · 出口(exit) —— REALITY 终端入站 |

## 工作原理

镜像是一层薄封装:多阶段构建从**按摘要锁定**的官方 Xray 镜像中复制 `xray` 二进制及其 `geoip.dat`/`geosite.dat`,因此二进制与上游逐字节一致。镜像本身只携带一个角色模板(`docker/templates/<role>.json`)、一份必填变量清单(`docker/vars/<role>.vars`)和一个共享的 `entrypoint.sh`。

启动时,entrypoint 会:

1. 检查角色必填清单中的每个变量是否已设置(缺失则中止并给出清晰提示);
2. 用 `envsubst` 渲染 JSONC 模板,且**仅限**清单中列出的变量白名单;
3. 运行 `xray run -test` 校验渲染后的配置 —— 配置有误会在代理启动**之前**中止;
4. `exec` 启动 xray。

设置 `SELFTEST=1` 会执行第 1–3 步后以 0 退出(构建冒烟测试使用)。若你在 `/etc/xray/config.json` 挂载了完整配置,entrypoint 会原样使用它并跳过渲染(仍会先 `run -test`)—— 这是应对特殊场景的逃生舱口。

## 快速开始

**镜像命名空间。** 镜像并未硬编码到任何 registry。两个开关,设成同一个值(你的 registry 命名空间,例如 `youruser/infra`):

- `REPO` —— 构建/推送时由 `scripts/build-images` 读取的环境变量。
- `IMAGE_REPO` —— 在每个节点的 `.env` 中设置;compose 文件会读取它(默认 `youruser/infra`)。这决定了节点在 `docker compose up` 时从哪个 registry 拉取。

### 构建与发布(维护者)

```sh
docker login -u <youruser>              # 自行执行;密码不要进入日志
REPO=<youruser>/infra scripts/build-images          # 构建 + 冒烟测试所有角色
REPO=<youruser>/infra scripts/build-images --push   # 再发布滚动标签 + 带日期标签
```

每个角色在推送**之前**都会用 `xray run -test`(使用一次性密钥)做冒烟测试,因此损坏的模板绝不会进入 registry。用 `XRAY_BASE=<ref>` 可覆盖基础镜像(例如本地已缓存的 `ghcr.io` 摘要);不设置时,默认使用 `docker/Dockerfile` 中的镜像源摘要。

### 拉起一个节点(运维,三步)

```sh
cd deploy/<role>/
cp ../../docker/env/<role>.env.example .env    # 然后填入真实值
# 在 .env 中把 IMAGE_REPO 设为你的命名空间(例如 youruser/infra)
docker compose up -d
```

`server-gate` 会运行两个容器:一个在 `127.0.0.1:GATE_PORT` 上的 REALITY 网关,以及一个监听 `:443` 的 nginx SNI 分流器 —— 匹配的 SNI 转发到网关,其余全部发往诱饵上游。完整运维指南见 [`deploy/README.md`](deploy/README.md),设计原理见 [`docs/design.md`](docs/design.md)。

## 配置参考

每个角色的变量都记录在 `docker/env/<role>.env.example` 中 —— 包括 `IMAGE_REPO`。将它复制为 `.env`,填好每一处 `REPLACE_ME`,并把结果**留在 git 之外**(`.env` 已被 gitignore)。用以下命令生成 REALITY 密钥对:

```sh
docker run --rm --entrypoint xray youruser/infra:server-exit x25519
```

## 安全与注意事项

- **本仓库是公开的。** 切勿提交真实端点、伪装用 serverName、UUID 或密钥。仓库中受版本控制的 `*.env.example` 仅为占位符;镜像不含任何密钥。
- **把填好的 `.env` 文件存放在本仓库之外** —— 用密钥管理器或加密存储。它们已被 gitignore,以便误 `git add` 时能被拦下。
- **`server-gate` / `server-exit` 模板是从实际拓扑重建的。** `xray run -test` 只能证明结构合法,并不保证语义一致 —— 生产切换前请逐字段核对你正在运行的 gate/exit 配置。
- **给 nginx 镜像锁定摘要**(在 `deploy/server-gate/docker-compose.yml` 中),在首次拉取之后进行;当前用版本标签只是为了避免 `:latest`。
- gate/exit 入站出现的 `REALITY: Listening on non-443 ports` 警告是预期内的 —— nginx 前置 `:443` 并把流量转发到环回地址上的网关。
