#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_cycles.py — 命題「週期型態」統計（**按科目獨立**）：由 corpus/tags_index.json
之題目參照（<等別>/<年>/<科目碼>#題號）計算每個考點（by_article／by_equipment／
by_topic）在**各等別各科目**的逐年出題序列，分類其出題型態，產出：

1. corpus/tags_cycles.json — 精簡週期索引（skill 可整檔載入）：
   {_meta, 等別: {科目: {維度: {tag: {years, n, first, last, gap_now, mean_gap, rate, pattern, codes}}}}}
2. corpus/命題週期分析.md — 人可讀報告：各等別 → 各科目之常年型／退役常年型／週期到期
   （回鍋候選）／新興熱點／冷卻中／一次性久未考清單，以及「未考缺口」。

**方法論（重要）**：每一科命題委員不同，統計一律**按科目（卷別）獨立**，不跨科合併；
同一條文若出現在不同科目（如 §14 於消防法規測驗卷與化學申論卷），各科各自計一條週期。
科目碼→科目名由 corpus/index.json 之 subject＋name 建映射。

型態分類規則（NEXT＝下一次考試年＝題庫最新年＋1；rate＝出現年數/該等別開辦年數）：
- 常年型     ：rate ≥ 0.5 且 gap_now ≤ 2 —— 幾乎每屆都考、近期仍在考，必練基本盤。
- 退役常年型 ：rate ≥ 0.5 且 gap_now ≥ 3 —— 曾每屆必考但近 ≥2 屆缺席，屬高信心回鍋候選。
- 新興熱點   ：mean_gap ≤ 1.5 且 gap_now ≤ 2 —— 近年開始後連續出題（常見於新修法考點）。
- 週期到期   ：n ≥ 2 且 gap_now ≥ max(mean_gap, 2) —— 已達/超過平均再現間隔，回鍋機率升高。
- 冷卻中     ：n ≥ 2 且 gap_now < mean_gap —— 剛考過不久，短期內再考機率較低。
- 一次性     ：n == 1 且 gap_now ≥ 5 —— 僅考過一次且久未再現，低優先。
- 偶發       ：其餘（樣本太少，不下結論）。

注意：型態為統計啟發式，僅供猜題排序參考，不是保證；與修法/函令/時事三維度合成使用。

用法：python3 scripts/analyze_cycles.py
"""
import json, re, pathlib, collections, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
IDX = ROOT / "corpus" / "tags_index.json"
INDEX = ROOT / "corpus" / "index.json"
CYCLES = ROOT / "corpus" / "tags_cycles.json"
REPORT = ROOT / "corpus" / "命題週期分析.md"
DEVICE_INDEX = ROOT / "reference" / "設備條文索引.md"

DIMS = ["by_article", "by_equipment", "by_topic"]
REF = re.compile(r"^(師|士)/(\d+)/(\d+)#")


def load_subject_map():
    """由 index.json 建 (等別, 科目碼) → 科目短名。短名去除『消防安全設備』贅字。"""
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    m = {}
    for p in data.get("papers", []):
        name = (p.get("name") or "").replace("消防安全設備", "")
        m[(p.get("level"), p.get("subject"))] = name
    return m


def classify(years, exam_years, next_year):
    n = len(years)
    first, last = years[0], years[-1]
    gap_now = next_year - last
    rate = n / len(exam_years)
    if n >= 2:
        gaps = [b - a for a, b in zip(years, years[1:])]
        mean_gap = round(statistics.mean(gaps), 2)
    else:
        mean_gap = None
    if rate >= 0.5 and gap_now <= 2:
        pattern = "常年型"
    elif rate >= 0.5 and gap_now >= 3:
        pattern = "退役常年型"     # 曾每屆必考、近 ≥2 屆缺席 → 高信心回鍋
    elif n >= 2 and mean_gap is not None and mean_gap <= 1.5 and gap_now <= 2:
        pattern = "新興熱點"       # 近年開始後連續出題（如新修法考點）
    elif n >= 2 and mean_gap is not None and gap_now >= max(mean_gap, 2):
        pattern = "週期到期"       # 已達/超過平均再現間隔
    elif n >= 2 and mean_gap is not None and gap_now < mean_gap:
        pattern = "冷卻中"
    elif n == 1 and gap_now >= 5:
        pattern = "一次性"
    else:
        pattern = "偶發"
    return {"years": years, "n": n, "first": first, "last": last,
            "gap_now": gap_now, "mean_gap": mean_gap,
            "rate": round(rate, 2), "pattern": pattern}


def main():
    idx = json.loads(IDX.read_text(encoding="utf-8"))
    code2subj = load_subject_map()

    # 各等別開辦年（由全部參照回推）
    level_years = collections.defaultdict(set)
    for dim in DIMS:
        for refs in idx.get(dim, {}).values():
            for r in refs:
                m = REF.match(r)
                if m:
                    level_years[m.group(1)].add(int(m.group(2)))

    out = {"_meta": {"rules": "常年型 rate>=0.5,gap_now<=2；退役常年型 rate>=0.5,gap_now>=3；"
                              "新興熱點 mean_gap<=1.5,gap_now<=2；週期到期 n>=2,gap_now>=max(mean_gap,2)；"
                              "冷卻中 n>=2,gap_now<mean_gap；一次性 n==1,gap_now>=5；其餘 偶發。"
                              "gap_now 以題庫最新年+1（下一次考試）計。**統計按科目（卷別）獨立，不跨科合併**。"}}

    for level, ys in sorted(level_years.items()):
        exam_years = sorted(ys)
        next_year = exam_years[-1] + 1
        out["_meta"][level] = {"exam_years": exam_years, "next_year": next_year}
        out[level] = {}
        for dim in DIMS:
            for tag, refs in idx.get(dim, {}).items():
                # 按科目分組（僅本等別），各科各自計一條週期
                by_subj = collections.defaultdict(lambda: {"years": set(), "codes": collections.Counter()})
                for r in refs:
                    m = REF.match(r)
                    if not m or m.group(1) != level:
                        continue
                    code = m.group(3)
                    subj = code2subj.get((level, code))
                    if not subj:
                        continue
                    by_subj[subj]["years"].add(int(m.group(2)))
                    by_subj[subj]["codes"][code] += 1
                for subj, info in by_subj.items():
                    years = sorted(info["years"])
                    if not years:
                        continue
                    rec = classify(years, exam_years, next_year)
                    rec["codes"] = dict(info["codes"].most_common())
                    out[level].setdefault(subj, {}).setdefault(dim, {})[tag] = rec

    CYCLES.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")

    # 缺口：設備條文索引之設置標準條號，題庫（師＋士合併）查無 by_article 者
    gaps = []
    if DEVICE_INDEX.exists():
        listed = set()
        for line in DEVICE_INDEX.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\|\s*設置標準\s*\|\s*([0-9\-]+)\s*\|", line)
            if m:
                listed.add(m.group(1))
        asked = set()
        for tag in idx.get("by_article", {}):
            m = re.match(r"^設置標準第([0-9\-]+)條$", tag)
            if m:
                asked.add(m.group(1))
        gaps = sorted(listed - asked, key=lambda x: [int(p) for p in x.split("-")])

    # 報告：各等別 → 各科目 → 各型態
    lines = ["# 命題週期分析", "",
             "> 由 `scripts/analyze_cycles.py` 自 `corpus/tags_index.json` 產生；型態分類規則見腳本檔首。"
             "**統計按科目（卷別）獨立**（每科命題委員不同，不跨科合併）。供 exam-trend-forecast 猜題參考，統計啟發式非保證。", ""]
    PATTERN_ORDER = [
        ("常年型", "常年型（幾乎每屆都考、近期仍在考——必練基本盤）", lambda t: -t[1]["rate"], 12),
        ("退役常年型", "退役常年型（曾每屆必考、近 ≥2 屆缺席——高信心回鍋）", lambda t: -t[1]["gap_now"], 12),
        ("新興熱點", "新興熱點（近年開始後連續出題，常見於新修法考點）", lambda t: -t[1]["n"], 10),
        ("週期到期", "週期到期（已達/超過平均再現間隔——回鍋候選）",
         lambda t: -(t[1]["gap_now"] - (t[1]["mean_gap"] or 0)), 15),
        ("冷卻中", "冷卻中（剛考過，依歷史間隔短期再考機率較低）", lambda t: t[1]["gap_now"], 10),
        ("一次性", "一次性久未考（低優先，除非修法/時事觸及）", lambda t: -t[1]["gap_now"], 10),
    ]
    for level in sorted(k for k in out if not k.startswith("_")):
        meta = out["_meta"][level]
        lines += [f"# {level}（開辦年 {meta['exam_years'][0]}–{meta['exam_years'][-1]}，"
                  f"下一次考試以 {meta['next_year']} 年計）", ""]
        for subj in sorted(out[level]):
            arts = out[level][subj].get("by_article", {})
            if not arts:
                continue
            lines += [f"## {subj}", ""]
            buckets = collections.defaultdict(list)
            for tag, rec in arts.items():
                buckets[rec["pattern"]].append((tag, rec))
            wrote_any = False
            for pat, title, sort_key, topn in PATTERN_ORDER:
                items = sorted(buckets.get(pat, []), key=sort_key)[:topn]
                if not items:
                    continue
                wrote_any = True
                lines += [f"### {title}", "",
                          "| 考點 | 出題年 | 次數 | 平均間隔 | 距今 |",
                          "| --- | --- | :---: | :---: | :---: |"]
                for tag, rec in items:
                    ys = "、".join(map(str, rec["years"]))
                    lines.append(f"| {tag} | {ys} | {rec['n']} | {rec['mean_gap'] or '—'} | {rec['gap_now']} |")
                lines.append("")
            if not wrote_any:
                lines += ["（本科 by_article 僅偶發樣本，略）", ""]
    if gaps:
        lines += ["# 未考缺口（設備條文索引有列，題庫全庫查無之設置標準條號）", "",
                  "> 從未出題之條文：搭配修法／函令／時事評估「首考」可能性；"
                  "多數屬細節條文，僅在動態維度觸及時上調。"
                  "**注意**：條號標籤僅在題目可明確對應條號時才標（申論題常僅標法規），"
                  "本清單為「查無條號標籤」而非嚴格「從未考過」，判讀時應以 by_law／"
                  "by_equipment 維度交叉確認。", "",
                  "設置標準：" + "、".join(f"§{g}" for g in gaps), ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK: {CYCLES.name} ({CYCLES.stat().st_size//1024} KB), {REPORT.name}; "
          f"levels={[k for k in out if not k.startswith('_')]}, 缺口={len(gaps)}")


if __name__ == "__main__":
    main()
