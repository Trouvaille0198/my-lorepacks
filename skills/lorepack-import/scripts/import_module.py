#!/usr/bin/env python3
"""lorepack-import — archive loreweaver-generated modules into my-lorepacks.

Scans the engine's `modules/` dir for `*.pack-src`, copies each into
`packs/<id>/pack-src`, builds the `.lwpack` into `dist/` (when missing), writes
a README from the lorecard, then commits and pushes the repo.

Paths come from `config.json` next to SKILL.md — run anywhere, adjust config.

Usage:
    import_module.py --scan                 # list unarchived modules
    import_module.py <pack-id> [--force]    # archive one module
    import_module.py --all [--force]        # archive every unarchived module
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

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
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if check and result.returncode != 0:
        sys.exit(f"命令失败: {' '.join(cmd)}\n{result.stderr[-1500:]}")
    return result.stdout.strip()


def scan(cfg: dict) -> list[str]:
    src = Path(cfg["module_source_dir"])
    if not src.is_dir():
        sys.exit(f"module_source_dir 不存在: {src}（检查 config.json）")
    packs = Path(cfg["lorepacks_repo"]) / "packs"
    found = sorted(p.stem for p in src.glob("*.pack-src"))
    archived = {p.name for p in packs.glob("*") if p.is_dir()}
    return [m for m in found if m not in archived]


def pack_version(pack_src: Path) -> str:
    manifest = pack_src / "pack.yaml"
    if manifest.is_file():
        m = re.search(r"^version:\s*(\S+)", manifest.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            return m.group(1)
    return "0.1.0"


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


def write_readme(pack_id: str, pack_src: Path, out: Path) -> None:
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
    assets = len(list((pack_src / "assets").glob("*.png"))) if (pack_src / "assets").is_dir() else 0
    skills = [d.name for d in (pack_src / "skills").glob("*") if d.is_dir()] if (pack_src / "skills").is_dir() else []

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
        parts = [f"{len(items)} 件"]
        if scope.get("universal"):
            parts.append(f"{scope['universal']} 件通用")
        if scope.get("module"):
            parts.append(f"{scope['module']} 件剧情")
        lines.append(f"- **物品**：{'（'.join(parts[:1])}" + (f"，{' / '.join(parts[1:])}" if len(parts) > 1 else "") + "）")
    lines.append(f"- **配图**：{assets} 张")
    if skills:
        lines.append(f"- **KP 技能**：{'、'.join(skills)}")
    lines += ["", "## 安装", "", "```", ".pack install gh:Trouvaille0198/my-lorepacks@<version>", "```", ""]
    out.write_text("\n".join(lines), encoding="utf-8")


def archive(cfg: dict, pack_id: str, *, force: bool) -> None:
    src_dir = Path(cfg["module_source_dir"])
    repo = Path(cfg["lorepacks_repo"])
    pack_src = src_dir / f"{pack_id}.pack-src"
    if not pack_src.is_dir():
        sys.exit(f"{pack_id}: 源 pack-src 不存在 {pack_src}")
    target = repo / "packs" / pack_id
    if target.exists() and not force:
        print(f"跳过 {pack_id}（已归档，--force 可覆盖）")
        return

    print(f"[{pack_id}] 复制 pack-src")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(pack_src, target / "pack-src")

    version = pack_version(target / "pack-src")
    dist = target / "dist" / f"{pack_id}-{version}.lwpack"
    existing = list((src_dir).glob(f"{pack_id}-*.lwpack"))
    if existing:
        shutil.copy2(existing[0], dist)
        print(f"  使用现有 .lwpack -> {dist}")
    else:
        ensure_manifest(target / "pack-src", pack_id)
        build_lwpack(cfg, pack_id, target / "pack-src", dist)

    print(f"[{pack_id}] 写 README")
    write_readme(pack_id, target / "pack-src", target / "README.md")

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


if __name__ == "__main__":
    main()
