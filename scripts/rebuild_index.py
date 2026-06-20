#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rebuild_index.py — 從各題 inline `🏷️` 標籤**反向建立** corpus/tags_index.json。

與 build_tags.py 的差異：build_tags.py 以關鍵字「自動判讀題目」產生標籤；本腳本
**不重新判讀題目**，只解析既有 inline 標籤（人工／語意校正後的結果即為唯一真相
來源），彙整成中央索引。語意校正分類請直接編輯各 md 的 `🏷️` 行，再執行本腳本。

用法：python3 scripts/rebuild_index.py
"""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MD_ROOT = ROOT / "corpus" / "md"
INDEX = ROOT / "corpus" / "tags_index.json"
TAG = "🏷️"

SYS_VOCAB = {"滅火設備", "警報設備", "避難逃生設備", "消防搶救上之必要設備", "綜合/通則"}
FLAG_VOCAB = {"找錯誤", "找正確", "計算題", "更正答案", "圖形題", "跨科"}
TYPE_VOCAB = {"申論題", "測驗題"}
ART_RE = re.compile(r"第\s*\d+\s*條")  # 條號標籤（法名＋第X條[之Y]）

# 設備、法規、知識領域詞彙取自 build_tags.py，確保與既有體系一致
import importlib.util
_spec = importlib.util.spec_from_file_location("build_tags", ROOT / "scripts" / "build_tags.py")
_bt = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_bt)
EQUIP_VOCAB = {name for _, name, _ in _bt.EQUIP}
LAW_VOCAB = {name for _, name in _bt.LAWS}
TOPIC_VOCAB = {name for _, name in _bt.TOPICS}


def dim_of(tok):
    if tok in TYPE_VOCAB: return "by_type"
    if tok in SYS_VOCAB: return "by_system"
    if tok in EQUIP_VOCAB: return "by_equipment"
    if tok in FLAG_VOCAB: return "by_flag"
    if ART_RE.search(tok): return "by_article"
    if tok in LAW_VOCAB: return "by_law"
    if tok in TOPIC_VOCAB: return "by_topic"
    return None  # 未知 token（可能為新法規短名／自訂），歸入 by_law 以免遺失


def main():
    idx = {k: {} for k in ("by_type", "by_system", "by_equipment", "by_law",
                           "by_article", "by_topic", "by_flag")}
    total = 0
    unknown = set()
    for md in sorted(MD_ROOT.rglob("*.md")):
        rel = md.relative_to(MD_ROOT)
        level, year = rel.parts[0], rel.parts[1]
        subject = md.stem.split("_")[0]
        paper = f"{level}/{year}/{subject}"
        lines = md.read_text(encoding="utf-8").split("\n")
        # 取得每個 🏷️ 行對應之題號：往上找最近的 ### 第N題 / 申論第N題
        qno = None
        for ln in lines:
            mo = re.match(r"^### 第\s*(\d+)\s*題", ln)
            me = re.match(r"^### 申論第([一二三四五六七八九十\d]+)題", ln)
            if mo: qno = f"#Q{mo.group(1)}"
            elif me:
                cn = {"一":1,"二":2,"三":3,"四":4,"五":5}
                qno = f"#甲{cn.get(me.group(1), me.group(1))}"
            s = ln.lstrip()
            if s.startswith(f"> {TAG}") or s.startswith(TAG):
                if qno is None: continue
                ref = paper + qno
                total += 1
                body = s.split(TAG, 1)[1].strip()
                for seg in body.split("｜"):
                    for tok in (t.strip() for t in seg.split("、")):
                        if not tok: continue
                        d = dim_of(tok)
                        if d is None:
                            unknown.add(tok); d = "by_law"
                        idx[d].setdefault(tok, []).append(ref)
    idx["_meta"] = {"total_questions": total, "generator": "scripts/rebuild_index.py",
                    "note": "由各題 inline 🏷️ 標籤解析而得；分類以 inline 標籤（語意校正後）為唯一真相來源"}
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"parsed {total} questions -> {INDEX.relative_to(ROOT)}")
    for k in ("by_type","by_system","by_equipment","by_law","by_article","by_topic","by_flag"):
        items = sorted(idx[k].items(), key=lambda x:-len(x[1]))
        head = [(t,len(v)) for t,v in items[:8]]
        print(f"  {k}: {len(idx[k])} 種；前8={head}")
    if unknown:
        print(f"  ⚠️ 未能歸類之 token（暫歸 by_law）：{sorted(unknown)}")


if __name__ == "__main__":
    main()
