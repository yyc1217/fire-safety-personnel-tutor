#!/usr/bin/env python3
"""比對 statutes/ 各 md 檔首版本日期與 docs/法規版本追蹤.md 核對紀錄表。

用法：
    python3 scripts/check_statute_versions.py               # 全部列出
    python3 scripts/check_statute_versions.py --stale-only  # 只列 🔴 過期與 ⚠️ 無法解析

狀態：
    🔴 過期＝本地版本早於「官方最新已知版本」
    ✅ 現行＝本地版本等於官方最新已知版本（以核對日期時點為準）
    ⚪ 未核對＝核對紀錄表無此檔
    ⚠️ 無法解析＝檔首版本日期非標準「民國 Y 年 M 月 D 日」格式
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUTES = ROOT / "statutes"
TRACKING = ROOT / "docs" / "法規版本追蹤.md"

DATE_RE = re.compile(r"民國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
DATE_SHORT_RE = re.compile(r"民國\s*(\d{2,3})-(\d{1,2})-(\d{1,2})")


def parse_date(text):
    """從文字取民國日期 → (年, 月, 日) tuple，取不到回 None。"""
    m = DATE_RE.search(text) or DATE_SHORT_RE.search(text)
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def local_version(path):
    """讀檔首前 5 行的「版本日期：…」。"""
    with open(path, encoding="utf-8") as f:
        head = "".join(f.readline() for _ in range(5))
    m = re.search(r"版本日期：([^\n｜|]*)", head)
    if not m:
        return None, None
    raw = m.group(1).strip()
    return raw, parse_date(raw)


def known_latest():
    """解析核對紀錄表：檔名 → (官方最新日期 tuple, 核對日期, 備註)。"""
    known = {}
    if not TRACKING.exists():
        return known
    in_table = False
    for line in TRACKING.read_text(encoding="utf-8").splitlines():
        if line.startswith("## 三、"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if not in_table or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("檔案", "------") or set(cells[0]) <= {"-"}:
            continue
        date = parse_date(cells[1])
        if date:
            known[cells[0]] = (date, cells[2], cells[3])
    return known


def main():
    stale_only = "--stale-only" in sys.argv
    known = known_latest()
    rows = []
    for path in sorted(STATUTES.glob("[12]_*.md")):
        raw, local = local_version(path)
        if local is None:
            status = "⚠️ 無法解析"
        elif path.name in known:
            official, checked, _ = known[path.name]
            if local < official:
                status = f"🔴 過期（官方 民國 {official[0]}-{official[1]:02d}-{official[2]:02d}，核對 {checked}）"
            else:
                status = f"✅ 現行（核對 {checked}）"
        else:
            status = "⚪ 未核對"
        rows.append((path.name, raw or "（檔首無版本日期）", status))

    shown = 0
    for name, raw, status in rows:
        if stale_only and not (status.startswith("🔴") or status.startswith("⚠️")):
            continue
        print(f"{status}\t{name}\t{raw}")
        shown += 1

    n_stale = sum(1 for _, _, s in rows if s.startswith("🔴"))
    n_unparsed = sum(1 for _, _, s in rows if s.startswith("⚠️"))
    n_unchecked = sum(1 for _, _, s in rows if s.startswith("⚪"))
    print(
        f"\n共 {len(rows)} 檔：🔴 過期 {n_stale}、⚠️ 無法解析 {n_unparsed}、"
        f"⚪ 未核對 {n_unchecked}、✅ 現行 {len(rows) - n_stale - n_unparsed - n_unchecked}",
        file=sys.stderr,
    )
    return 1 if n_stale else 0


if __name__ == "__main__":
    sys.exit(main())
