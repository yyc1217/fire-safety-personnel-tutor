#!/usr/bin/env python3
"""把本 plugin 的 skills 安裝到 Claude Code 以外的 AI agent（通用版 Agent Skills）。

Claude Code 會在叫用 SKILL.md 時代入 `${CLAUDE_PLUGIN_ROOT}`、`${user_config.*}` 等變數；
其他 agent 不會。本腳本把 `skills/` 下各 skill 複製到指定的 skills 目錄，並於複本中：

- `${CLAUDE_PLUGIN_ROOT}/skills/` → 安裝目標目錄（指向代入後的複本）
- `${CLAUDE_PLUGIN_ROOT}`       → 本資料夾的絕對路徑（題庫、法規、reference 皆留在原處）
- `${user_config.*}`           → 命令列參數之值（未給則留空，首次使用時由 agent 詢問）
- `${CLAUDE_SESSION_ID}`       → 空白
- frontmatter 移除 Claude Code 專屬欄位（allowed-tools、context、background）
- 於內文開頭加註通用版環境說明（`$ARGUMENTS`、`/fs-*` 指令之意義與資料根目錄）

只用 Python 標準函式庫，可重複執行（每次皆由原始 `skills/` 重新產生）。

    python3 install.py --target ~/.agents/skills
    python3 install.py --target ./.agents/skills --level 士 --weakness-tracking auto
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 通用版 zip 中本檔位於根目錄；於 git clone 中則位於 scripts/
ROOT = HERE if (HERE / "skills").is_dir() else HERE.parent

DROP_KEYS = {"allowed-tools", "context", "background"}


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end < 0:
        return text
    kept: list[str] = []
    dropping = False
    for line in text[4:end].split("\n"):
        key = re.match(r"^([A-Za-z0-9_-]+):", line)
        if key:
            dropping = key.group(1) in DROP_KEYS
        elif not line.startswith((" ", "\t", "-")):
            dropping = False
        if not dropping:
            kept.append(line)
    return "---\n" + "\n".join(kept) + text[end:]


def notice(root: str) -> str:
    return (
        "> **通用版環境說明**（由 install.py 加註，非 Claude Code 環境適用）：\n"
        f"> 本 plugin 之資料根目錄為 `{root}`，題庫（`corpus/`）、法規（`statutes/`）、"
        "`reference/` 皆在其下；其他檔案中出現之 `${CLAUDE_PLUGIN_ROOT}` 一律指此目錄。\n"
        "> 文中 `$ARGUMENTS` 指使用者叫用本 skill 時附帶之參數（取自使用者訊息，未附帶即視為未指定）；"
        "`/fs-xxx` 指令即叫用同名 skill。\n"
        "> `${CLAUDE_SESSION_ID}` 於本環境無值，依規格省略該欄。\n\n"
    )


def transform(text: str, *, root: str, target: str, values: dict[str, str], is_skill: bool) -> str:
    text = text.replace("${CLAUDE_PLUGIN_ROOT}/skills/", target + "/")
    text = text.replace("${CLAUDE_PLUGIN_ROOT}", root)
    for key, val in values.items():
        text = text.replace("${user_config.%s}" % key, val)
    text = text.replace("${CLAUDE_SESSION_ID}", "")
    if is_skill:
        text = strip_frontmatter(text)
        end = text.find("\n---\n", 4) if text.startswith("---\n") else -1
        cut = end + len("\n---\n") if end >= 0 else 0
        text = text[:cut] + notice(root) + text[cut:]
    return text


def install(target: Path, values: dict[str, str]) -> list[str]:
    target.mkdir(parents=True, exist_ok=True)
    root = ROOT.as_posix()
    tgt = target.resolve().as_posix()
    names: list[str] = []
    for src in sorted((ROOT / "skills").iterdir()):
        if not (src / "SKILL.md").is_file():
            continue
        dst = target / src.name
        if dst.exists():
            shutil.rmtree(dst)
        for f in src.rglob("*"):
            out = dst / f.relative_to(src)
            if f.is_dir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            if f.suffix == ".md":
                text = f.read_text(encoding="utf-8")
                text = transform(text, root=root, target=tgt, values=values, is_skill=f.name == "SKILL.md" and f.parent == src)
                out.write_text(text, encoding="utf-8")
            else:
                shutil.copy2(f, out)
        names.append(src.name)
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description="把消防設備師／士備考 skills 安裝到其他 AI agent 的 skills 目錄。")
    ap.add_argument("--target", action="append", required=True, type=Path,
                    help="agent 讀取 skill 的目錄（可重複指定多個），例：~/.agents/skills")
    ap.add_argument("--level", default="", choices=["", "師", "士"], help="應考等別；留空則首次使用時詢問")
    ap.add_argument("--weakness-tracking", default="", choices=["", "auto", "notes", "none"],
                    help="弱點記錄模式；留空則首次使用時詢問")
    ap.add_argument("--data-dir", default="~/.fire-safety-tutor", help="學習資料目錄（預設 ~/.fire-safety-tutor）")
    args = ap.parse_args()

    if not (ROOT / "skills").is_dir():
        print(f"找不到 skills/：{ROOT}", file=sys.stderr)
        return 1
    values = {
        "level": args.level,
        "weakness_tracking": args.weakness_tracking,
        "data_dir": Path(args.data_dir).expanduser().as_posix(),
    }
    for t in args.target:
        t = t.expanduser()
        names = install(t, values)
        print(f"已安裝 {len(names)} 個 skill 至 {t.resolve()}：{'、'.join(names)}")
    print(f"資料根目錄：{ROOT}（請勿搬移或刪除；搬移後重新執行本腳本即可）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
