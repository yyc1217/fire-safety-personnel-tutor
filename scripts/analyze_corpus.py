#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_corpus.py — 由 corpus/tags_index.json 計算命題頻率與難易度趨勢，產出：

1. corpus/tags_summary.json — **精簡計數索引**（各維度 tag→總數、逐年數、師/士數），
   不含題目參照陣列，檔案小，供 skill（尤其 exam-trend-forecast）直接載入做統計，
   毋需載入完整 tags_index.json（見「載入策略」）。
2. corpus/命題頻率分析.md — 人可讀之頻率/趨勢報告。

題目參照格式：`<等別>/<年>/<科目代碼>#Q<題號>`（申論 `#甲<n>`），年為民國年。

載入策略（tags_index.json 載入優化）：
- 總覽／頻率統計 → 載入 corpus/tags_summary.json（小）。
- 取某 tag 之題目清單 → 對 corpus/tags_index.json 用 jq 取單鍵，勿全檔載入：
    jq '.by_equipment["自動撒水設備"]' corpus/tags_index.json
- 取某題完整內容 → 由參照推出檔路徑，讀該 md。

用法：python3 scripts/analyze_corpus.py
"""
import json, re, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
IDX = ROOT / "corpus" / "tags_index.json"
SUMMARY = ROOT / "corpus" / "tags_summary.json"
REPORT = ROOT / "corpus" / "命題頻率分析.md"

REF = re.compile(r"^(師|士)/(\d+)/")

DIMS = ["by_type", "by_system", "by_equipment", "by_law", "by_article", "by_topic", "by_flag"]


def parse(ref):
    m = REF.match(ref)
    return (m.group(1), m.group(2)) if m else (None, None)


def main():
    idx = json.loads(IDX.read_text(encoding="utf-8"))
    years = set()
    for dim in DIMS:
        for refs in idx.get(dim, {}).values():
            for r in refs:
                lv, yr = parse(r)
                if yr: years.add(yr)
    years = sorted(years, key=int)

    summary = {"_meta": {"total_questions": idx.get("_meta", {}).get("total_questions"),
                         "years": years, "generator": "scripts/analyze_corpus.py"}}
    for dim in DIMS:
        summary[dim] = {}
        for tag, refs in idx.get(dim, {}).items():
            by_year = collections.Counter()
            by_level = collections.Counter()
            for r in refs:
                lv, yr = parse(r)
                if yr: by_year[yr] += 1
                if lv: by_level[lv] += 1
            summary[dim][tag] = {"total": len(refs),
                                 "師": by_level.get("師", 0), "士": by_level.get("士", 0),
                                 "by_year": dict(sorted(by_year.items(), key=lambda x: int(x[0])))}
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- 人可讀報告 ----
    def table(dim, title, topn=None):
        items = sorted(summary[dim].items(), key=lambda x: -x[1]["total"])
        if topn: items = items[:topn]
        out = [f"### {title}", "", "| 項目 | 總數 | 師 | 士 |", "|---|---|---|---|"]
        for t, d in items:
            out.append(f"| {t} | {d['total']} | {d['師']} | {d['士']} |")
        return "\n".join(out) + "\n"

    def year_trend(dim, keys, title):
        out = [f"### {title}（逐年）", "", "| 年 | " + " | ".join(keys) + " |",
               "|---|" + "|".join(["---"] * len(keys)) + "|"]
        for y in years:
            row = [y] + [str(summary[dim].get(k, {}).get("by_year", {}).get(y, 0)) for k in keys]
            out.append("| " + " | ".join(row) + " |")
        return "\n".join(out) + "\n"

    tot = summary["_meta"]["total_questions"]
    md = [f"# 命題頻率與難易度分析\n",
          f"> 由 `scripts/analyze_corpus.py` 自 `corpus/tags_index.json` 產生；總題數 {tot}。",
          f"> 資料為歷年考古題標籤統計，年為民國年（{years[0]}–{years[-1]}）。供 exam-trend-forecast 參考；"
          f"現行命題趨勢仍應以官方最新命題大綱與近年實際考題為準。\n", "---\n",
          "## 一、各維度出題次數（總計）\n",
          table("by_system", "系統（對應設備師4系統考科）"),
          table("by_equipment", "消防安全設備種類"),
          table("by_law", "法規依據", topn=25),
          table("by_topic", "火災學知識領域"),
          table("by_article", "最常考條號（前 25）", topn=25),
          "## 二、難易度／題型趨勢（逐年）\n",
          year_trend("by_type", ["申論題", "測驗題"], "題型"),
          year_trend("by_flag", ["計算題", "找錯誤", "找正確", "更正答案"], "旗標"),
          "## 三、系統別逐年出題\n",
          year_trend("by_system", ["水系統", "化學系統", "警報系統", "避難系統"], "系統"),
          ]
    REPORT.write_text("\n".join(md), encoding="utf-8")
    print(f"OK：{SUMMARY.relative_to(ROOT)}（{SUMMARY.stat().st_size} bytes）、{REPORT.relative_to(ROOT)}")
    print(f"  年度範圍 {years[0]}–{years[-1]}，總題數 {tot}")


if __name__ == "__main__":
    main()
