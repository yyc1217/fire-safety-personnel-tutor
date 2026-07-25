#!/usr/bin/env python3
"""repo 完整性與格式檢查（CI 用，亦可本機執行）。

只做**機械可驗**的檢查，不觸碰內容正確性（法條數值、標籤語意等仍靠人工）。

    python3 scripts/ci_check_repo.py            # 全部檢查
    python3 scripts/ci_check_repo.py --list     # 列出可用檢查
    python3 scripts/ci_check_repo.py -k links   # 只跑名稱含 links 的檢查

有任何 ERROR 時以 1 結束；WARN 不影響結束碼。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 內容資料夾：格式規範（上標、全形編號括號）適用範圍
CONTENT_DIRS = ["statutes", "corpus", "reference"]

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def md_files(dirs: list[str]) -> list[Path]:
    out: list[Path] = []
    for d in dirs:
        out.extend(sorted((ROOT / d).rglob("*.md")))
    return out


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


# --------------------------------------------------------------------------
# 1. plugin / marketplace 資訊清單
# --------------------------------------------------------------------------
def check_manifests() -> None:
    """plugin.json 與 marketplace.json 之 schema 與跨檔一致性。"""
    pj_path = ROOT / ".claude-plugin" / "plugin.json"
    mp_path = ROOT / ".claude-plugin" / "marketplace.json"

    try:
        pj = json.loads(read(pj_path))
    except Exception as e:  # noqa: BLE001
        err(f"plugin.json 無法解析：{e}")
        return
    try:
        mp = json.loads(read(mp_path))
    except Exception as e:  # noqa: BLE001
        err(f"marketplace.json 無法解析：{e}")
        return

    if "name" not in pj:
        err("plugin.json 缺必填欄位 name")

    version = pj.get("version")
    if version and not re.fullmatch(r"\d+\.\d+\.\d+", version):
        err(f"plugin.json version 非 semver：{version!r}")

    for field in ("description", "keywords"):
        if field not in pj:
            warn(f"plugin.json 建議補上 {field}")

    names = [p.get("name") for p in mp.get("plugins", [])]
    if pj.get("name") not in names:
        err(
            f"marketplace.json 未列出本 plugin：plugin.json name={pj.get('name')!r}，"
            f"marketplace 條目={names}"
        )

    # 版本唯一真相在 plugin.json；marketplace 條目不得另立版本造成漂移
    for entry in mp.get("plugins", []):
        if entry.get("name") == pj.get("name") and "version" in entry:
            err(
                "marketplace.json 條目重複宣告 version，會與 plugin.json 漂移；"
                "版本請只留在 plugin.json"
            )

    # README badge 需與 plugin.json 同版
    if version:
        readme = read(ROOT / "README.md")
        badge = re.search(r"badge/version-([0-9.]+)-", readme)
        if not badge:
            warn("README.md 找不到 version badge")
        elif badge.group(1) != version:
            err(
                f"版本不一致：plugin.json={version}，README badge={badge.group(1)}"
                "（改動 skills／reference／corpus／statutes 時記得同步 bump 兩處）"
            )


# --------------------------------------------------------------------------
# 2. skill frontmatter
# --------------------------------------------------------------------------
def parse_frontmatter(text: str) -> dict | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    body = text[4:end]
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    try:
        return yaml.safe_load(body) or {}
    except Exception:  # noqa: BLE001
        return None


def check_skills() -> None:
    """每個 skill 需有可解析的 frontmatter 與 description。"""
    skill_dirs = sorted(d for d in (ROOT / "skills").iterdir() if d.is_dir())
    if not skill_dirs:
        err("skills/ 下沒有任何 skill")
        return

    for d in skill_dirs:
        f = d / "SKILL.md"
        if not f.exists():
            err(f"{rel(d)} 缺 SKILL.md")
            continue
        fm = parse_frontmatter(read(f))
        if fm is None:
            err(f"{rel(f)} frontmatter 無法解析")
            continue
        if not fm:
            continue  # 無 PyYAML，跳過細項
        if not fm.get("description"):
            err(f"{rel(f)} 缺 description（Claude 據此判斷何時載入）")
        desc = str(fm.get("description", "")) + str(fm.get("when_to_use", ""))
        if len(desc) > 1536:
            err(f"{rel(f)} description 長度 {len(desc)} 超過官方 1,536 字上限，會被截斷")
        at = fm.get("allowed-tools")
        if at is not None and not isinstance(at, list):
            err(f"{rel(f)} allowed-tools 應為 YAML 清單（含空白的規則如 'Bash(jq *)' 不可用空白分隔字串）")

    # README 宣稱的 slash command 數量需與實際相符
    readme = read(ROOT / "README.md")
    cmd_count = sum(
        1
        for d in skill_dirs
        if (d / "SKILL.md").exists()
        and "disable-model-invocation: true" in read(d / "SKILL.md")
    )
    core_count = len(skill_dirs) - cmd_count
    zh = "零一二三四五六七八九十"
    expect_core = zh[core_count] if core_count < len(zh) else str(core_count)
    expect_cmd = zh[cmd_count] if cmd_count < len(zh) else str(cmd_count)
    claim = re.search(r"([零一二三四五六七八九十]+)個功能 skill＋([零一二三四五六七八九十]+)個 slash command skill", readme)
    if not claim:
        warn("README.md 找不到 skill 數量敘述，無法比對")
    elif (claim.group(1), claim.group(2)) != (expect_core, expect_cmd):
        err(
            f"README skill 數量與實際不符：README 稱 {claim.group(1)}＋{claim.group(2)}，"
            f"實際 {expect_core}（功能）＋{expect_cmd}（slash command）"
        )


# --------------------------------------------------------------------------
# 3. corpus 索引
# --------------------------------------------------------------------------
def check_corpus_index() -> None:
    """corpus/index.json 每筆試卷之檔案路徑須實際存在。"""
    idx = ROOT / "corpus" / "index.json"
    try:
        data = json.loads(read(idx))
    except Exception as e:  # noqa: BLE001
        err(f"corpus/index.json 無法解析：{e}")
        return

    papers = data.get("papers", [])
    if not papers:
        err("corpus/index.json 的 papers 為空")
        return

    for p in papers:
        tag = f"{p.get('level')}/{p.get('year')}/{p.get('subject')}"
        for field in ("md", "pdf", "ans_pdf", "mod_ans_pdf"):
            v = p.get(field)
            if v and not (ROOT / "corpus" / v).exists():
                err(f"corpus/index.json {tag} 的 {field} 指向不存在的檔案：{v}")


# --------------------------------------------------------------------------
# 4. 文件內部連結
# --------------------------------------------------------------------------
PLACEHOLDER = re.compile(r"[<>…\*\?]|\.\.\.|｜")
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FENCE = re.compile(r"(?ms)^```.*?^```")
INLINE_CODE = re.compile(r"`[^`\n]*`")
# 只有結尾的 ` "標題"` 才是 markdown title，路徑本身可含空白（如「第 18 條完整條文.pdf」）
LINK_TITLE = re.compile(r"\s+[\"'(].*$")


def check_links() -> None:
    """markdown 相對連結（含圖片）須指向存在的檔案。"""
    from urllib.parse import unquote

    targets = md_files(["skills", "reference", "docs", "corpus", "statutes"]) + [
        ROOT / "README.md",
        ROOT / ".claude" / "CLAUDE.md",
        ROOT / "CHANGELOG.md",
    ]
    for f in targets:
        if not f.exists():
            continue
        # 程式碼區塊與行內 code 多為範例路徑（如 `![說明](檔名.png)`），不檢查
        text = INLINE_CODE.sub("", FENCE.sub("", read(f)))
        for m in LINK.finditer(text):
            target = LINK_TITLE.sub("", m.group(1)).strip().strip("<>")
            if (
                target.startswith(("http://", "https://", "#", "mailto:"))
                or PLACEHOLDER.search(target)
            ):
                continue
            path = target.split("#")[0]
            if not path:
                continue
            if not (f.parent / unquote(path)).exists():
                err(f"{rel(f)} 連結指向不存在的路徑：{target}")


# --------------------------------------------------------------------------
# 5. 格式規範（CLAUDE.md 之機械可驗部分）
# --------------------------------------------------------------------------
# 「任何有平方的數字／單位一律以上標 ² 表示」——適用所有內容資料夾
SQUARED = re.compile(r"(?<![A-Za-z0-9])((?:c|m|k|d)?m|kgf/cm|N/mm)([23])(?![0-9A-Za-z\-])")

# 「條文階層編號之括號一律使用全形（）」——**只適用 statutes/**（法規條文）。
# corpus/ 的 (A)(B)(C)(D) 是考卷選項標記、reference/輸出格式/ 是選項版面範本，
# 兩者都不是條文階層編號，不受此規範。
HALFWIDTH_NUM = re.compile(
    r"(?m)^\s*(?:[-*>|]\s*)?\((?:[一二三四五六七八九十]+|\d{1,2})\)\s*[、\s]"
)


def check_format_rules() -> None:
    """上標（全內容資料夾）與條文階層編號全形括號（僅 statutes/）。"""
    for f in md_files(CONTENT_DIRS):
        text = read(f)
        for m in SQUARED.finditer(text):
            line = text[: m.start()].count("\n") + 1
            err(
                f"{rel(f)}:{line} 平方／立方未用上標：{m.group(0)!r} "
                f"（應寫成 {m.group(1)}{'²' if m.group(2) == '2' else '³'}）"
            )

    for f in md_files(["statutes"]):
        text = read(f)
        for m in HALFWIDTH_NUM.finditer(text):
            line = text[: m.start()].count("\n") + 1
            err(f"{rel(f)}:{line} 條文階層編號使用半形括號：{m.group(0).strip()!r}（應改全形（））")


# --------------------------------------------------------------------------
CHECKS = {
    "manifests": check_manifests,
    "skills": check_skills,
    "corpus-index": check_corpus_index,
    "links": check_links,
    "format-rules": check_format_rules,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="列出可用檢查後結束")
    ap.add_argument("-k", metavar="SUBSTR", help="只跑名稱含 SUBSTR 的檢查")
    args = ap.parse_args()

    if args.list:
        for name, fn in CHECKS.items():
            print(f"{name:<14} {(fn.__doc__ or '').splitlines()[0]}")
        return 0

    selected = {n: f for n, f in CHECKS.items() if not args.k or args.k in n}
    if not selected:
        print(f"沒有符合 {args.k!r} 的檢查", file=sys.stderr)
        return 2

    for name, fn in selected.items():
        before = len(errors)
        fn()
        status = "FAIL" if len(errors) > before else "ok"
        print(f"[{status:>4}] {name}")

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")

    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
