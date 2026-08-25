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
- README 的安装命令用 `gh:Trouvaille0198/my-lorepacks@<version>`（GitHub release 分发，release 需另行打）
- 已归档的模组（`packs/<id>/` 已存在）会被跳过，除非显式传 `--force`
- 引擎数据目录里被中断的生成（有 pack-src 但无 .lwpack）也可以入库——脚本会先构建
