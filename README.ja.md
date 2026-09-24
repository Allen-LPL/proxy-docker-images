# proxy-docker-images

**言語:** [English](README.md) · [简体中文](README.zh-CN.md) · 日本語

Xray ベースのプロキシサービスチェーン向けの、パラメータ化された再利用可能な Docker イメージ。ダイジェスト固定(digest-pinned)された 1 つの Xray コアをロールごとにラップし、各ノードは短い `.env` を記入して `docker compose up` を実行するだけで起動できます。**シークレットがイメージレイヤーや本リポジトリに残ることは一切ありません。**

## イメージの中身

5 つのロール、それぞれに 1 つのイメージ(あなた自身の registry に公開、例:`<youruser>/infra:<role>`):

| ロール | 内容 |
|---|---|
| `client-legacy` | 旧クライアント —— 単一のグローバル VMess 出口、分流ルーティングなし |
| `client` | 新クライアント —— AI トラフィックは二層 REALITY チェーン経由、その他は既定の出口経由 |
| `server-legacy` | 旧サーバー —— VMess インバウンド |
| `server-gate` | 新サーバー・ゲート —— nginx SNI スプリッタの背後にある REALITY ゲート |
| `server-exit` | 新サーバー・出口 —— REALITY 終端インバウンド |

## 仕組み

イメージは薄いラッパーです。マルチステージビルドで、**ダイジェスト固定**された公式 Xray イメージから `xray` バイナリとその `geoip.dat`/`geosite.dat` をコピーするため、バイナリは上流とバイト単位で同一です。イメージ自体はロールのテンプレート(`docker/templates/<role>.json`)、必須変数リスト(`docker/vars/<role>.vars`)、共有の `entrypoint.sh` だけを持ちます。

起動時、entrypoint は次を行います:

1. ロールの必須リストにある各変数が設定されているか確認する(未設定なら明確なメッセージを出して中断);
2. `envsubst` で JSONC テンプレートをレンダリングする。ただし、それらの変数だけを許可する**許可リスト**に限定する;
3. `xray run -test` を実行してレンダリング済み設定を検証する —— 不正な設定はプロキシ起動の**前に**中断する;
4. xray を `exec` する。

`SELFTEST=1` を設定すると 1〜3 の手順を実行して 0 で終了します(ビルドのスモークテストで使用)。`/etc/xray/config.json` に完全な設定をマウントすると、entrypoint はそれをそのまま使用しレンダリングをスキップします(それでも先に `run -test` を実行します)—— 特殊ケース向けの脱出ハッチです。

## クイックスタート

**イメージの名前空間。** イメージはどの registry にもハードコードされていません。2 つのスイッチを、同じ値(あなたの registry の名前空間、例:`youruser/infra`)に設定します:

- `REPO` —— ビルド/プッシュ時に `scripts/build-images` が読み取る環境変数。
- `IMAGE_REPO` —— 各ノードの `.env` に設定;compose ファイルがこれを読み取る(既定は `youruser/infra`)。これが `docker compose up` でノードがどこから取得するかを決めます。

### ビルドと公開(メンテナー)

```sh
docker login -u <youruser>              # 自分で実行;パスワードはログに残さない
REPO=<youruser>/infra scripts/build-images          # 全ロールをビルド + スモークテスト
REPO=<youruser>/infra scripts/build-images --push   # その後ローリングタグ + 日付タグを公開
```

各ロールはプッシュの**前に** `xray run -test`(使い捨てのシークレットを使用)でスモークテストされるため、壊れたテンプレートが registry に届くことはありません。`XRAY_BASE=<ref>` でベースイメージを上書きできます(例:ローカルにキャッシュされた `ghcr.io` のダイジェスト);未設定の場合は `docker/Dockerfile` にあるミラーのダイジェストが既定になります。

### ノードを起動する(オペレーター、3 ステップ)

```sh
cd deploy/<role>/
cp ../../docker/env/<role>.env.example .env    # その後、実際の値を記入
# .env で IMAGE_REPO をあなたの名前空間に設定(例:youruser/infra)
docker compose up -d
```

`server-gate` は 2 つのコンテナを実行します:`127.0.0.1:GATE_PORT` 上の REALITY ゲートと、`:443` を待ち受ける nginx SNI スプリッタ —— 一致した SNI はゲートへ転送し、それ以外はすべてデコイの上流へ送ります。完全なオペレーターガイドは [`deploy/README.md`](deploy/README.md) を、設計の背景は [`docs/design.md`](docs/design.md) を参照してください。

## 設定リファレンス

各ロールの変数は `docker/env/<role>.env.example` に記載されています —— `IMAGE_REPO` を含みます。これを `.env` にコピーし、すべての `REPLACE_ME` を記入し、結果を **git の外に**保管してください(`.env` は gitignore 済み)。REALITY 鍵ペアは次で生成します:

```sh
docker run --rm --entrypoint xray youruser/infra:server-exit x25519
```

## セキュリティと注意事項

- **本リポジトリは公開です。** 実際のエンドポイント、カモフラージュ用 serverName、UUID、鍵を絶対にコミットしないでください。バージョン管理下の `*.env.example` はプレースホルダーのみで、イメージにシークレットは含まれません。
- **記入済みの `.env` ファイルはこのリポジトリの外に保管してください** —— シークレットマネージャーまたは暗号化ストレージで。これらは gitignore 済みのため、誤った `git add` を検知できます。
- **`server-gate` / `server-exit` テンプレートは実際のトポロジから再構築されました。** `xray run -test` は構造的な妥当性を証明しますが、意味的な一致は保証しません —— 本番切り替えの前に、稼働中の gate/exit 設定とフィールドごとに照合してください。
- **nginx イメージにはダイジェストを固定してください**(`deploy/server-gate/docker-compose.yml` 内)。初回取得の後に行います;現在のバージョンタグは `:latest` を避けるためだけのものです。
- gate/exit インバウンドで出る `REALITY: Listening on non-443 ports` の警告は想定内です —— nginx が `:443` を前面に置き、ループバック上のゲートへ転送します。
