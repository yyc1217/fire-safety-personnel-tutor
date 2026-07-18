#!/usr/bin/env python3
"""audit_article_tags.py — 盤查「題幹 vs 條文要旨」一致性（一次性檢查工具）。

背景：inline 🏷️ 之條號標籤有兩種來源——題幹自帶「第N條」（自動擷取），或
依題旨人工補號。前者的風險是 statutes 現行編號漂移（見 #29），後者的風險是
補錯條（見 #30）。本腳本把每筆「題×條號」參照展開為：
    參照ID｜條號標籤｜題幹｜statutes 對應條文全文｜是否題幹自帶該號
輸出 JSON 供人工/模型逐筆判讀題旨是否與條文相符。

用法：python3 scripts/audit_article_tags.py > /tmp/audit.json
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_ROOT = ROOT / "corpus" / "md"
STATUTES = ROOT / "statutes"
TAG = "🏷️"

# 條號標籤前綴 → statutes 檔（涵蓋 tags_index 全部 12 種前綴）
PREFIX2FILE = {
    "設置標準": "2_01_各類場所消防安全設備設置標準.md",
    "消防法": "1_01_消防法.md",
    "施行細則": "1_02_消防法施行細則.md",
    "建築技術規則建築設計施工編": "3_02_建築技術規則建築設計施工編.md",
    "建築技術規則": "3_02_建築技術規則建築設計施工編.md",
    "公危辦法": "1_10_公共危險物品及可燃性高壓氣體製造儲存處理場所設置標準暨安全管理辦法.md",
    "建築法": "3_01_建築法.md",
    "檢修專業機構管理辦法": "1_08_消防安全設備檢修專業機構管理辦法.md",
    "消防安全設備檢修專業機構管理辦法": "1_08_消防安全設備檢修專業機構管理辦法.md",
    "防火牆及防火水幕設置基準": "1_12_防火牆及防火水幕設置基準.md",
    "複合用途建築物判斷基準": "2_04_複合用途建築物判斷基準.md",
    "測試報告書": "2_10_消防安全設備測試報告書測試方法及判定要領.md",
}

ART_TAG_RE = re.compile(r"^(.+?)第\s*(\d+(?:-\d+)?|[〇零一二三四五六七八九十百]+)\s*條(之\s*\d+)?$")
ART_HEAD_RE = re.compile(r"^##\s*第\s*(\d+(?:-\d+)?)\s*條")


def load_statute_articles(fn):
    """回傳 {條號字串: 條文全文}。條號字串如 '199'、'111-1'。"""
    path = STATUTES / fn
    if not path.exists():
        return {}
    arts, cur, buf = {}, None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ART_HEAD_RE.match(line)
        if m:
            if cur is not None:
                arts[cur] = "\n".join(buf).strip()
            cur = m.group(1)
            buf = []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        arts[cur] = "\n".join(buf).strip()
    return arts


_STATUTE_CACHE = {}


def get_article_text(prefix, num):
    fn = PREFIX2FILE.get(prefix)
    if not fn:
        return None, f"(未知法規前綴：{prefix})"
    if fn not in _STATUTE_CACHE:
        _STATUTE_CACHE[fn] = load_statute_articles(fn)
    arts = _STATUTE_CACHE[fn]
    txt = arts.get(num)
    if txt is None:
        return fn, f"(在 {fn} 查無第 {num} 條)"
    return fn, txt


def parse_tag_articles(tagline):
    """從標籤行的欄位中抽出條號標籤（含『第N條』者）。"""
    body = tagline.split(TAG, 1)[1]
    out = []
    for field in body.split("｜"):
        # 同一題多條號會用「、」併進同一欄位，需再切開
        for item in field.split("、"):
            item = item.strip()
            m = ART_TAG_RE.match(item)
            if m:
                prefix = m.group(1)
                num = m.group(2)
                sub = m.group(3)
                numkey = num
                if sub:
                    numkey = f"{num}-{sub.replace('之','').strip()}"
                out.append((item, prefix, numkey))
    return out


def iter_questions(md_path):
    """逐題產生 (ref, 題幹block, tagline)。

    題號解析對齊 rebuild_index.py：測驗題 `### 第<阿拉伯>題`→#QN；
    申論題 `### 申論第N題` 或全申論卷之 `### 第<中文>題`→#甲N。
    """
    rel = md_path.relative_to(MD_ROOT)
    level, year = rel.parts[0], rel.parts[1]
    subject = md_path.stem.split("_")[0]
    paper = f"{level}/{year}/{subject}"
    lines = md_path.read_text(encoding="utf-8").split("\n")
    n = len(lines)
    cn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

    def qno_of(ln):
        mo = re.match(r"^### 第\s*(\d+)\s*題", ln)
        me = re.match(r"^### 申論第([一二三四五六七八九十\d]+)題", ln)
        mc = re.match(r"^### 第([一二三四五六七八九十]+)題", ln)
        if mo:
            return f"#Q{mo.group(1)}"
        if me:
            return f"#甲{cn.get(me.group(1), me.group(1))}"
        if mc:
            return f"#甲{cn.get(mc.group(1), mc.group(1))}"
        return None

    i = 0
    while i < n:
        q = qno_of(lines[i])
        if q:
            j = i + 1
            buf = []
            while j < n and qno_of(lines[j]) is None and not lines[j].startswith("## "):
                buf.append(lines[j])
                j += 1
            block = "\n".join(buf)
            tagline = next((b for b in buf if TAG in b), "")
            yield paper + q, block, tagline
            i = j
            continue
        i += 1


def main():
    records = []
    for md in sorted(MD_ROOT.rglob("*.md")):
        for ref, block, tagline in iter_questions(md):
            if not tagline:
                continue
            arts = parse_tag_articles(tagline)
            if not arts:
                continue
            # 題幹（去掉標籤行本身）
            stem = "\n".join(b for b in block.split("\n") if TAG not in b).strip()
            for field, prefix, numkey in arts:
                fn, text = get_article_text(prefix, numkey)
                # 題幹是否自帶此條號（判斷是自動擷取或人工補號）
                num_plain = numkey.split("-")[0]
                in_stem = bool(re.search(r"第\s*" + re.escape(num_plain) + r"\s*條", stem))
                records.append({
                    "ref": ref,
                    "tag": field,
                    "prefix": prefix,
                    "num": numkey,
                    "statute_file": fn,
                    "in_stem": in_stem,
                    "stem": stem,
                    "article_text": text,
                })
    print(json.dumps(records, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()


# ── 反查：在該法規全文中找與題幹最相符之條文（偵測條號漂移用） ──
def _bigrams(s):
    s = re.sub(r"[\s\W_0-9A-Za-z（）()、，。：；「」【】〔〕．·　]", "", s)
    return set(s[i:i+2] for i in range(len(s) - 1))


def best_match_article(prefix, stem):
    """回傳 (最佳條號, 分數)；在該法規所有條文中找與題幹 bigram 重疊最高者。"""
    fn = PREFIX2FILE.get(prefix)
    if not fn:
        return None, 0.0
    if fn not in _STATUTE_CACHE:
        _STATUTE_CACHE[fn] = load_statute_articles(fn)
    sb = _bigrams(stem)
    if not sb:
        return None, 0.0
    best, bestscore = None, 0.0
    for num, txt in _STATUTE_CACHE[fn].items():
        ab = _bigrams(txt)
        if not ab:
            continue
        score = len(sb & ab) / min(len(sb), len(ab))
        if score > bestscore:
            best, bestscore = num, score
    return best, bestscore
