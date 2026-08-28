#!/usr/bin/env python3
"""lorepack-import — archive loreweaver-generated modules into my-lorepacks.

Scans the engine's `modules/` dir (or a Docker container's `/data/packs/`)
for module sources, copies each into `packs/<id>/pack-src`, cleans the forge
manifest into author form, builds the `.lwpack` into `dist/`, writes a README
from the lorecard, then commits and pushes the repo. `--release` publishes the
built `.lwpack` as a GitHub release asset (`gh:` installs resolve through it).

Paths come from `config.json` next to SKILL.md — run anywhere, adjust config.

Usage:
    import_module.py --scan                 # list unarchived modules
    import_module.py <pack-id> [--force]    # archive one module
    import_module.py <pack-id> --release    # archive and publish a GitHub release
    import_module.py --all [--force]        # archive every unarchived module
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    cfg_path = SKILL_DIR / "config.json"
    if not cfg_path.exists():
        sys.exit(
            f"缺少 config.json：复制 {SKILL_DIR / 'config_example.json'} 为 config.json 并填写路径"
        )
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)


def run(cmd: list[str], cwd: Path, *, check: bool = True) -> str:
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        sys.exit(f"命令失败: {' '.join(cmd)}\n{result.stderr[-1500:]}")
    return result.stdout.strip()


def scan(cfg: dict) -> list[str]:
    container = cfg.get("docker_container")
    if container:
        out = run(
            ["docker", "exec", container, "sh", "-c", "ls /data/packs/"],
            Path.cwd(), check=False,
        )
        found = sorted({p.split("@")[0] for p in out.split() if "@" in p})
    else:
        src = Path(cfg["module_source_dir"])
        if not src.is_dir():
            sys.exit(f"module_source_dir 不存在: {src}（检查 config.json）")
        found = sorted(p.stem for p in src.glob("*.pack-src"))
    packs = Path(cfg["lorepacks_repo"]) / "packs"
    archived = {p.name for p in packs.glob("*") if p.is_dir()}
    return [m for m in found if m not in archived]


def pack_version(pack_src: Path) -> str:
    manifest = pack_src / "pack.yaml"
    if manifest.is_file():
        m = re.search(r"^version:\s*(\S+)", manifest.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            return m.group(1)
    return "0.1.0"


def clean_manifest(pack_src: Path) -> None:
    """把 forge 产物 pack.yaml 清洗成 author 侧格式：删 `files`/`trust`（打包时
    生成）、`contents.cards` 去掉 `kind`（打包时按真实载荷检测）。asset 的
    sha256/size/mime/title 可保留。"""
    manifest = pack_src / "pack.yaml"
    if not manifest.is_file():
        return
    raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return
    changed = False
    for key in ("files", "trust"):
        if key in raw:
            del raw[key]
            changed = True
    contents = raw.get("contents")
    cards = contents.get("cards") if isinstance(contents, dict) else None
    if isinstance(cards, list):
        cleaned: list = []
        for entry in cards:
            if isinstance(entry, dict):
                cleaned.append(entry.get("path"))
                changed = True
            else:
                cleaned.append(entry)
        if changed and contents is not None:
            contents["cards"] = cleaned
    if changed:
        manifest.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        print("  pack.yaml 已清洗为 author 侧格式（删 files/trust、cards 去 kind）")


def ensure_manifest(pack_src: Path, pack_id: str) -> Path:
    """Return the pack's manifest, generating one from the lorecard when the
    pack-src is an interrupted forge product (assets+cards only, no pack.yaml /
    skills — the media pass finished but the build step never ran)."""
    manifest = pack_src / "pack.yaml"
    if manifest.is_file():
        return manifest
    cards = sorted((pack_src / "cards").glob("*.lorecard.json"))
    if not cards:
        sys.exit(f"{pack_id}: pack-src 没有 cards/*.lorecard.json，无法生成 manifest")
    card = json.loads(cards[0].read_text(encoding="utf-8"))
    name = str(card.get("name") or pack_id)
    name_en = str(card.get("name_en") or pack_id)
    description = str(card.get("description") or "")
    assets = sorted(p.relative_to(pack_src).as_posix() for p in (pack_src / "assets").glob("*") if p.is_file())
    lines = [
        "manifest_version: 2",
        f"id: {pack_id}",
        f"version: {pack_version(pack_src)}",
        "name:",
        f"  en: {name_en}",
        f"  zh: {name}",
        "description:",
        f"  en: {description}",
        "authors: [Trouvaille0198]",
        "license: CC-BY-4.0",
        "contents:",
        "  cards:",
        f"    - {cards[0].relative_to(pack_src).as_posix()}",
    ]
    if assets:
        lines.append("assets:")
        lines.extend(f"  - path: {a}" for a in assets)
    lines.append("")
    manifest.write_text("\n".join(lines), encoding="utf-8")
    print(f"  pack-src 缺 pack.yaml（中断产物），已从 lorecard 生成 manifest（{len(assets)} 资产）")
    return manifest


def copy_pack_src(cfg: dict, pack_id: str, target: Path) -> None:
    """把 pack-src 复制到 target/pack-src：配置了 docker_container 时优先从容器
    `/data/packs/<id>@<version>/` 取（配图后完整版），否则从本地 modules/ 取。
    forge 的 `media-jobs.json` 是运行时状态，不复制。"""
    container = cfg.get("docker_container")
    if container:
        out = run(
            ["docker", "exec", container, "sh", "-c", f"ls -d /data/packs/{pack_id}@* 2>/dev/null"],
            Path.cwd(), check=False,
        )
        if not out:
            sys.exit(f"{pack_id}: 容器 {container} 里没有 /data/packs/{pack_id}@*")
        src_dir = out.splitlines()[0].strip()
        print(f"  从容器复制 pack-src（{src_dir}）")
        run(["docker", "cp", f"{container}:{src_dir}/.", str(target / "pack-src")], Path.cwd())
    else:
        src_dir = Path(cfg["module_source_dir"]) / f"{pack_id}.pack-src"
        if not src_dir.is_dir():
            sys.exit(f"{pack_id}: 源 pack-src 不存在 {src_dir}")
        print(f"  复制 pack-src（{src_dir}）")
        shutil.copytree(src_dir, target / "pack-src")
    runtime = target / "pack-src" / "media-jobs.json"
    if runtime.exists():
        runtime.unlink()


def fill_skills_from_container(cfg: dict, pack_src: Path) -> None:
    """pack.yaml 声明了 contents.skills 但 pack-src 里没有 skills/ 目录时，从容器
    `/data/skills/<id>/` 补齐（运行时技能装在数据目录，不在包目录里）。"""
    container = cfg.get("docker_container")
    manifest = pack_src / "pack.yaml"
    if not container or not manifest.is_file():
        return
    raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    contents = raw.get("contents") or {}
    for skill_id in contents.get("skills") or []:
        sid = str(skill_id).strip("/").split("/")[-1]
        dst = pack_src / "skills" / sid
        if dst.exists():
            continue
        out = run(
            ["docker", "exec", container, "sh", "-c", f"ls /data/skills/{sid}/SKILL.md 2>/dev/null"],
            Path.cwd(), check=False,
        )
        if out:
            dst.mkdir(parents=True, exist_ok=True)
            run(["docker", "cp", f"{container}:/data/skills/{sid}/SKILL.md", str(dst / "SKILL.md")], Path.cwd())
            print(f"  从容器补齐技能 {sid}")


def build_lwpack(cfg: dict, pack_id: str, pack_src: Path, out: Path) -> None:
    engine = Path(cfg["engine_repo"])
    if not (engine / ".venv" / "bin" / "python").exists():
        sys.exit(f"engine_repo 下没有 .venv：{engine}（构建 .lwpack 需要引擎）")
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"  构建 .lwpack -> {out}")
    run(
        [
            str(engine / ".venv" / "bin" / "python"),
            "-m",
            "app",
            "--pack",
            str(pack_src),
            "--out",
            str(out),
        ],
        engine,
    )


def ensure_lfs(repo: Path) -> None:
    """仓库根没有跟踪 *.lwpack 时初始化 Git LFS。超过 GitHub 100MB 单文件上限的
    .lwpack 必须走 LFS，否则 push 被 pre-receive hook 拒绝。"""
    attrs = repo / ".gitattributes"
    if attrs.is_file() and "*.lwpack" in attrs.read_text(encoding="utf-8"):
        return
    if shutil.which("git-lfs") is None:
        print("  ⚠ 未安装 git-lfs：>100MB 的 .lwpack 推不上 GitHub（pre-receive hook 拒绝）")
        print("    安装：从 https://github.com/git-lfs/git-lfs/releases 下载 linux-amd64 二进制放 ~/.local/bin")
        return
    run(["git", "lfs", "install", "--skip-repo"], repo)
    run(["git", "lfs", "track", "*.lwpack"], repo)


_ART_KIND_LABELS = [("cover", "封面"), ("scenes", "场景"), ("npcs", "NPC"), ("items", "物品"), ("pregens", "调查员")]


def _skill_display_name(skill_dir: Path) -> str:
    """SKILL.md frontmatter 的 name（如「南洋苍凉诡谲」），取不到则回退目录名。"""
    md = skill_dir / "SKILL.md"
    if md.is_file():
        m = re.search(r"^name:\s*['\"]?([^'\"]+?)['\"]?\s*$", md.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            return m.group(1).strip()
    return skill_dir.name


def _art_detail(pack_src: Path) -> str:
    """按 assets 路径分类统计配图明细，如「12 张（封面 + 2 场景 + 4 NPC + 1 物品 + 6 调查员）」。
    分类不出时回退为纯张数。"""
    manifest = pack_src / "pack.yaml"
    if manifest.is_file():
        paths = re.findall(r"path:\s*(\S+)", manifest.read_text(encoding="utf-8"))
    else:
        paths = [p.name for p in (pack_src / "assets").glob("*")] if (pack_src / "assets").is_dir() else []
    if not paths:
        return "0 张"
    counts = {kind: 0 for kind, _ in _ART_KIND_LABELS}
    for p in paths:
        base = Path(p).name
        for kind, _ in _ART_KIND_LABELS:
            if f"-{kind}-" in base:
                counts[kind] += 1
                break
    detail = " + ".join(f"{counts[kind]} {label}" for kind, label in _ART_KIND_LABELS if counts[kind])
    return f"{len(paths)} 张（{detail}）" if detail else f"{len(paths)} 张"


def write_readme(pack_id: str, pack_src: Path, out: Path, version: str) -> None:
    cards = list((pack_src / "cards").glob("*.lorecard.json"))
    if not cards:
        sys.exit(f"{pack_id}: pack-src 里没有 cards/*.lorecard.json")
    card = json.loads(cards[0].read_text(encoding="utf-8"))
    name = str(card.get("name") or pack_id)
    desc = str(card.get("description") or "")
    scenario = str(card.get("scenario") or "")
    worldbook = len(card.get("worldbook") or [])
    variables = len(card.get("variables") or [])
    pregens = [str(p.get("name")) for p in card.get("pregens") or [] if isinstance(p, dict) and p.get("name")]
    items = card.get("items") or []
    from collections import Counter

    scope = Counter(str(i.get("scope")) for i in items if isinstance(i, dict))
    art = _art_detail(pack_src)
    skills = [_skill_display_name(d) for d in (pack_src / "skills").glob("*") if d.is_dir()] if (pack_src / "skills").is_dir() else []

    lines = [
        f"# {name}（{pack_id}）",
        "",
        desc,
        "",
        scenario,
        "",
        "## 内容",
        "",
        f"- **世界设定（worldbook）**：{worldbook} 条",
        f"- **类型变量**：{variables} 个进度追踪器",
        f"- **预建调查员**：{len(pregens)} 名（{'、'.join(pregens)}）" if pregens else f"- **预建调查员**：{len(pregens)} 名",
    ]
    if items:
        scope_parts = [f"{scope[k]} 件{label}" for k, label in (("universal", "通用"), ("module", "剧情")) if scope.get(k)]
        line = f"- **物品**：{len(items)} 件"
        if scope_parts:
            line += f"（{' + '.join(scope_parts)}）"
        lines.append(line)
    lines.append(f"- **配图**：{art}")
    if skills:
        lines.append(f"- **KP 技能**：{'、'.join(skills)}")
    lines += ["", "## 安装", "", "```", f".pack install gh:Trouvaille0198/my-lorepacks@{version}", "```", ""]
    out.write_text("\n".join(lines), encoding="utf-8")


def publish_release(cfg: dict, pack_id: str, version: str) -> None:
    repo = Path(cfg["lorepacks_repo"])
    dist = repo / "packs" / pack_id / "dist" / f"{pack_id}-{version}.lwpack"
    if not dist.is_file():
        sys.exit(f"{pack_id}: 没有 {dist}，无法发布 release")
    if shutil.which("gh") is None:
        sys.exit("未安装 gh CLI（发布 release 需要）。登录：gh auth login --web --skip-ssh-key")
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-m", f"release {pack_id} v{version}（dist .lwpack）", "--allow-empty"], repo)
    run(["git", "push", "origin", cfg.get("default_branch", "main")], repo)
    print(f"[{pack_id}] 发布 GitHub release {version}")
    run(["gh", "release", "create", version, str(dist), "--repo", "Trouvaille0198/my-lorepacks"], repo)


def archive(cfg: dict, pack_id: str, *, force: bool) -> None:
    repo = Path(cfg["lorepacks_repo"])
    target = repo / "packs" / pack_id
    if target.exists() and not force:
        print(f"跳过 {pack_id}（已归档，--force 可覆盖）")
        return

    print(f"[{pack_id}] 复制 pack-src")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    copy_pack_src(cfg, pack_id, target)

    pack_src = target / "pack-src"
    ensure_manifest(pack_src, pack_id)
    clean_manifest(pack_src)
    fill_skills_from_container(cfg, pack_src)

    version = pack_version(pack_src)
    dist = target / "dist" / f"{pack_id}-{version}.lwpack"
    build_lwpack(cfg, pack_id, pack_src, dist)

    print(f"[{pack_id}] 写 README")
    write_readme(pack_id, pack_src, target / "README.md", version)

    ensure_lfs(repo)
    branch = cfg.get("default_branch", "main")
    print(f"[{pack_id}] commit + push")
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-m", f"add {pack_id} content pack v{version}"], repo)
    run(["git", "pull", "origin", branch, "--rebase"], repo)
    run(["git", "push", "origin", branch], repo)
    print(f"[{pack_id}] 完成 ✅")


def main() -> None:
    cfg = load_config()
    args = sys.argv[1:]
    if "--scan" in args:
        pending = scan(cfg)
        if not pending:
            print("没有待入库模组（全部已归档）")
        else:
            print("待入库模组:")
            for m in pending:
                print(f"  - {m}")
        return
    force = "--force" in args
    release = "--release" in args
    ids = [a for a in args if not a.startswith("--")]
    if "--all" in args:
        ids = scan(cfg)
        if not ids:
            print("没有待入库模组")
            return
    if not ids:
        sys.exit(__doc__ or "usage: import_module.py <pack-id> | --all | --scan")
    for pack_id in ids:
        archive(cfg, pack_id, force=force)
        if release:
            version = pack_version(Path(cfg["lorepacks_repo"]) / "packs" / pack_id / "pack-src")
            publish_release(cfg, pack_id, version)


if __name__ == "__main__":
    main()
