#!/usr/bin/env python3
"""build_article_list.py — 產生「法規條文清單索引」。

用途：`/掌握度` 消防法規段需列出各法規「全部條文」畫覆蓋度熱區圖。為避免
每次呈現重掃 statutes 全文，先由本腳本解析各法規 md 的結構單位（條／章）
一次算出有序清單，輸出 reference/索引/法規條文清單索引.md，呈現時只讀此索引。

只處理 by_law 出題頻率前 5 大法規（見 TOP5）。指名其他法規時由 skill
當場讀該法 statutes（單一法規，成本低），不預存。

修法後重跑：python3 scripts/build_article_list.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUTES = ROOT / "statutes"

# 法規名 → statutes 檔案（by_law 前 5 大）
TOP5 = [
    ("各類場所消防安全設備設置標準", "2_01_各類場所消防安全設備設置標準.md"),
    ("公共危險物品及可燃性高壓氣體製造儲存處理場所設置標準暨安全管理辦法",
     "1_10_公共危險物品及可燃性高壓氣體製造儲存處理場所設置標準暨安全管理辦法.md"),
    ("消防法", "1_01_消防法.md"),
    ("消防安全設備及必要檢修項目檢修基準", "2_03_消防安全設備及必要檢修項目檢修基準.md"),
    ("建築技術規則建築設計施工編", "3_02_建築技術規則建築設計施工編.md"),
]

ART = re.compile(r"^##\s*第\s*(\d+(?:-\d+)?)\s*條")          # 條（含 N-M＝之M）
CHAP = re.compile(r"^##\s*第([〇零一二三四五六七八九十百]+)章")   # 章（檢修基準）


CHAP_H1 = re.compile(r"^#\s+.+　第([〇零一二三四五六七八九十百]+)章")   # 拆章檔之 H1


def parse(md: Path):
    arts, chaps = [], []
    for line in md.read_text(encoding="utf-8").splitlines():
        m = ART.match(line)
        if m:
            arts.append(m.group(1))
            continue
        c = CHAP.match(line)
        if c:
            chaps.append(c.group(1))
    if not arts and not chaps:
        # 逐章拆檔法規（如檢修基準）：hub 檔無章標題，改讀同名子資料夾各章檔之 H1
        # （子資料夾與 hub 主檔同名，含編號前綴，見 CLAUDE.md「資產資料夾規則」）
        split_dir = md.parent / md.stem
        if split_dir.is_dir():
            for f in sorted(split_dir.glob("第*章*.md")):
                h1 = f.read_text(encoding="utf-8").split("\n", 1)[0]
                c = CHAP_H1.match(h1)
                if c:
                    chaps.append(c.group(1))
    def dedup(seq):  # 保序去重（statutes 偶有重複標題）
        seen, out = set(), []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out
    if arts:
        return "條", dedup(arts)
    return "章", dedup(chaps)


def main():
    out = ["# 法規條文清單索引（掌握度熱區圖之條文骨架）",
           "",
           "> 📌 由 `scripts/build_article_list.py` 解析 `statutes/` 產生，僅涵蓋 `by_law`"
           " 出題頻率**前 5 大法規**。`/掌握度` 消防法規段用本索引列出各法「全部條文」"
           "畫覆蓋度熱區圖，**呈現時只讀本索引、不重掃 statutes 全文**；指名前 5 以外之"
           "法規時，由 skill 當場讀該法 statutes（單一法規、成本低）。",
           ">",
           "> 本索引只列**條文骨架**（有哪些條/章）；各條之掌握度分子（已掌握要點）與分母"
           "（該條要點總數，語意切分）由 exam-tutor 批改時存入 `progress.json` 之 `coverage`"
           "（見 `reference/user-config-spec.md`），本索引不含要點數。",
           ">",
           "> **條號 key 對應**：條號 `N-M` 即「第 N 條之 M」，coverage key 用"
           "`by_article:<法規短名>第N條之M`（對齊 `corpus/tags_index.json` 維度，如"
           "`設置標準第111條之1`，不用 `111-1`）；檢修基準以章為單位，key＝"
           "`by_article:檢修基準第X章`（中文數字）。見 `reference/user-config-spec.md`。",
           ">",
           "> ⚠️ 條號隨修法可能變動，修法後請重跑腳本更新。",
           ""]
    for name, fn in TOP5:
        md = STATUTES / fn
        if not md.exists():
            print(f"WARN 找不到 {md}", file=sys.stderr)
            continue
        unit, items = parse(md)
        out.append(f"## {name}")
        out.append(f"- 結構單位：{unit}｜共 {len(items)} {unit}")
        if unit == "條":
            out.append("- 條號：" + "、".join(items))
        else:
            out.append("- 章：" + "、".join(f"第{c}章" for c in items))
        out.append("")
    (ROOT / "reference" / "索引" / "法規條文清單索引.md").write_text("\n".join(out), encoding="utf-8")
    print("已寫出 reference/索引/法規條文清單索引.md")


if __name__ == "__main__":
    main()
