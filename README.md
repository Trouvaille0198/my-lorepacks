# my-lorepacks

Trouvaille0198 的个人 Loreweaver 内容包（`.lwpack`）仓库。

每个目录（`packs/<pack-id>/`）是一个 Loreweaver 内容包：

- `pack-src/` — 可重建的包源码（`pack.yaml` manifest + `cards/` + `assets/` + `skills/` 等）
- `dist/<pack-id>-<version>.lwpack` — 打包产物
- `README.md` — 该包说明

## 从本仓库安装一个包

`.lwpack` 通过 **GitHub release asset** 分发，用 `gh:` 直链导入：

```
.pack install gh:Trouvaille0198/my-lorepacks            # 最新 release
.pack install gh:Trouvaille0198/my-lorepacks@0.1.0      # 指定 release
```

`resolve_pack_ref` 会拉取该 release 的 `*.lwpack` asset 并安装。

## 添加一个新包

1. 在 `packs/<pack-id>/` 下放源码（`pack-src/`）
2. 构建 `.lwpack`：`python -m app --pack packs/<pack-id>/pack-src --out packs/<pack-id>/dist/<id>-<ver>.lwpack`
3. commit + push 源码
4. 打 GitHub release，把 `dist/*.lwpack` 挂为 release asset
