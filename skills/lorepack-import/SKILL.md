---
name: lorepack-import
description: 把引擎（loreweaver）生成的模组加入 my-lorepacks 内容包仓库：复制 pack-src、构建 .lwpack、写 README、commit + push。路径全部走 config.json，可在任意机器上执行。
---

# Lorepack Import

把 loreweaver 引擎生成的模组（`pack-src` 目录）归档进 my-lorepacks 内容包仓库的标准流程。

## 前置要求

1. 引擎仓库（含 `python -m app --pack`，用于从 pack-src 构建 `.lwpack`）
2. my-lorepacks 仓库（目标）
3. 引擎数据目录（`modules/` 下是生成的 `*.pack-src`）

## 配置

复制 `config_example.json` 为 `config.json` 并填写：

```bash
cp config_example.json config.json
```

### config.json 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `engine_repo` | string | 是 | 引擎仓库路径（含 `.venv` 或已装依赖，构建 .lwpack 用） |
| `module_source_dir` | string | 是 | 引擎数据目录下的 `modules/` 目录（生成模组的 pack-src 所在处） |
| `lorepacks_repo` | string | 是 | my-lorepacks 仓库路径 |
| `default_branch` | string | 否 | 推送分支，默认 `main` |

## 使用方法

### 列出待入库模组

```bash
python3 scripts/scan.py
```

### 入库单个模组

```bash
python3 scripts/import_module.py <pack-id>
# 例：python3 scripts/import_module.py tide-of-grayrock
```

### 入库全部未归档模组

```bash
python3 scripts/import_module.py --all
```

## 流程（import_module.py 内部步骤）

对每个模组 `<pack-id>`：

1. **定位**：`<module_source_dir>/<pack-id>.pack-src` 必须存在，否则报错跳过
2. **复制源码**：`pack-src/` → `<lorepacks_repo>/packs/<pack-id>/pack-src/`
3. **构建 .lwpack**（若 `<module_source_dir>` 下没有现成 `.lwpack`）：
   ```bash
   cd <engine_repo> && .venv/bin/python -m app --pack <pack-src> --out <lorepacks_repo>/packs/<pack-id>/dist/<pack-id>-<version>.lwpack
   ```
   version 从 pack-src 的 `pack.yaml` 读取
4. **写 README.md**：从 `pack-src/cards/*.lorecard.json` 提取：
   - 模组名（`name`）与英文名（`name_en`）
   - 剧情简介（`description` + `scenario`）
   - worldbook 条数、变量数、预建调查员名单、物品数（含 scope 分布）、配图数、KP 技能 id
   - 按既有包（如 `packs/under-the-sea-fog/README.md`）的格式生成
5. **git 提交推送**：
   ```bash
   cd <lorepacks_repo> && git add -A && git commit -m "add <name> (<pack-id>) content pack v<version>"
   git pull origin main --rebase && git push origin main
   ```

## 参数说明（import_module.py）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--all` | 否 | 入库所有尚未归档的 pack-src |
| `<pack-id>` | - | 指定单个模组 id（pack-src 目录名去掉 `.pack-src`） |

## 注意事项

- **路径全部来自 config.json**——在别的机器/别的位置执行时，先改 config.json，不要改脚本
- pack-src 里有 `assets/`（配图）、`cards/*.lorecard.json`、`skills/`、`pack.yaml`，全部复制
- README 的安装命令用 `gh:Trouvaille0198/my-lorepacks@<version>`（GitHub release 分发，`--release` 参数自动发布）

## 实战要点

### 数据源优先用 Docker 容器里的完整版

引擎 Docker 部署时，配图已生成的完整模组在容器 `/data/packs/<id>@<version>/`，本机 `modules/` 里的 `.pack-src` 可能是配图前的旧版（没有 `assets/`）。配置 `docker_container` 后脚本优先从容器取；容器包目录里没有 `skills/`——KP 技能装在 `/data/skills/<skill-id>/`，脚本按 pack.yaml 的 `contents.skills` 声明从容器补齐，sha256 必须与声明一致（用 `sha256sum` 核对）。

### pack.yaml 是 forge 产物时先清洗成 author 侧格式

打包器（`core/pack.py`）对 author 侧 manifest 拒绝三样，forge 生成的 pack.yaml 全中：

- `contents.cards` 里的 `kind:` 声明——卡类型在打包时按真实载荷检测，author 侧只能写纯路径（或 `{path, notes}`）
- `files:` 段——打包时自动生成
- `trust:` 段——打包时自动生成

`assets` 的 `sha256`/`size`/`mime`/`title` 可以留。不删这三样 `python -m app --pack` 直接报错。`--force` 重入库时脚本会再次清洗。

### 超过 100MB 的 .lwpack 走 Git LFS

GitHub 单文件上限 100MB，超出后 push 被 `pre-receive hook declined` 拒绝（不显示具体原因）。仓库根要有 `.gitattributes` 跟踪 `*.lwpack`，大文件以 LFS pointer 入库。git-lfs 没装时从 GitHub release 下载官方二进制放到 `~/.local/bin`（免 sudo），`git lfs install --skip-repo` 即可。脚本会在 commit 前确保 LFS 已配置。

### release 是分发通道

`.pack install gh:owner/repo@<tag>` 走的是 GitHub release asset（匿名 API 解析该 release 的 `*.lwpack`），不是 git 仓库里的文件。tag 必须与 `@` 后面的字符串精确匹配——README 写 `@0.1.0` 时 release tag 就叫 `0.1.0`。用 `--release` 参数发布：

```bash
python3 scripts/import_module.py <pack-id> --release
```

gh 登录用 `gh auth login --hostname github.com --git-protocol ssh --web --skip-ssh-key`，`--skip-ssh-key` 避免 SSH key 上传交互卡住（device code 流程在无 TTY 后台时输出到 stderr，需重定向文件读取）。
