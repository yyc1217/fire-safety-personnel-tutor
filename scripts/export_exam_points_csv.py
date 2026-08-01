#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_exam_points_csv.py — 將考點分桶結果匯出為單一 CSV（試算表可直接開）。

資料來源：corpus/repeat_granularity.json（由 analyze_repeat_granularity.py 產生）
          scripts/repeat_lexicon.json（取各桶之比對關鍵字，供人工核對分類）

一列 = 等別 × 系統 × 顆粒度層 × 考點；只輸出「師」「士」兩等別（命題委員不同，
不輸出合併列，避免同一考點重複計數；合併數字仍存於 repeat_granularity.json）。

⚠️ 本檔為**探索性分析**之匯出：分桶採關鍵字啟發式（非語意標籤），設備／組件層
未分類率偏高，欄位「層未分類率%」「層判讀」即為此提示。結論一律以官方公告之
命題大綱與現行法規為準，本檔不得回寫 tags_index.json／inline 🏷️ 標籤。

用法：
    python3 scripts/export_exam_points_csv.py
    python3 scripts/export_exam_points_csv.py --scopes 師 士 合併   # 需要合併列時
"""

import os
import csv
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_JSON = os.path.join(ROOT, "corpus", "repeat_granularity.json")
LEXICON = os.path.join(ROOT, "scripts", "repeat_lexicon.json")
OUT_CSV = os.path.join(ROOT, "corpus", "考點清單.csv")

LADDER = ["設備", "組件", "子考點", "子子考點"]
RECENT_WINDOW = 5  # 「近N年考過年數」之視窗

HEADER = [
    "等別", "系統", "顆粒度層", "考點",
    "考過年數", "出現年份", "最早考過年", "最近考過年",
    "距今未考年數", f"近{RECENT_WINDOW}年考過年數",
    "層題數", "層未分類率%", "層觀測重考率%", "層隨機基準%", "層判讀",
    "比對關鍵字", "資料來源",
]


def verdict(perm):
    """依置換檢定給白話判讀（與 analyze_repeat_granularity.py 一致，去除 markdown 強調）。"""
    if not perm:
        return "樣本不足，無法檢定"
    obs, mean, pct = perm.get("observed"), perm.get("null_mean"), perm.get("percentile")
    if obs is None or mean is None:
        return "樣本不足，無法檢定"
    if pct is None:
        return ""
    if pct < 2.5:
        return "顯著低於隨機（疑有迴避傾向，仍須注意樣本）"
    if pct < 5:
        return "略低於隨機（單尾邊緣，樣本小，多屬雜訊）"
    if pct > 95:
        return "顯著高於隨機（比隨機更常重考）"
    return "與隨機無異（重考率下降＝顆粒度機率，非迴避）"


def rate(v):
    return f"{v:.1f}" if isinstance(v, (int, float)) else ""


def keywords_of(lex, sysname, layer, bucket):
    """取該桶在詞庫中的關鍵字；底線開頭之控制鍵（_gate/_focus）不在此列。"""
    ld = lex["systems"].get(sysname, {}).get("layers", {}).get(layer, {})
    kws = ld.get(bucket)
    return ";".join(kws) if isinstance(kws, list) else ""


def latest_year(data):
    """語料中最新的民國年，作為「距今未考年數」之基準。"""
    years = [y
             for sysres in data["systems"].values()
             for layres in sysres.values()
             for sc in layres["scopes"].values()
             for ys in sc.get("buckets", {}).values()
             for y in ys]
    return max(years) if years else None


def build_rows(data, lex, scopes):
    base = latest_year(data)
    rows = []
    for sysname, sysres in data["systems"].items():
        for layer in LADDER:
            layres = sysres.get(layer)
            if not layres:
                continue
            for scope in scopes:
                sc = layres["scopes"].get(scope)
                if not sc or not sc.get("buckets"):
                    continue
                perm = sc.get("perm")
                layer_cols = [
                    sc.get("n", ""),
                    rate(sc.get("unclassified_rate")),
                    rate(sc.get("repeat_rate")),
                    rate(perm.get("null_mean")) if perm else "",
                    verdict(perm),
                ]
                for bucket, years in sc["buckets"].items():
                    recent = sum(1 for y in years if y > base - RECENT_WINDOW)
                    rows.append([
                        scope, sysname, layer, bucket,
                        len(years), ";".join(map(str, years)),
                        min(years), max(years),
                        base - max(years), recent,
                        *layer_cols,
                        keywords_of(lex, sysname, layer, bucket),
                        "corpus/repeat_granularity.json",
                    ])
    # 等別 → 系統 → 層（依 LADDER）→ 考過年數多者先 → 考點
    sys_order = list(data["systems"])
    scope_order = list(scopes)
    rows.sort(key=lambda r: (scope_order.index(r[0]), sys_order.index(r[1]),
                             LADDER.index(r[2]), -r[4], r[3]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scopes", nargs="+", default=["師", "士"],
                    help="要輸出的等別（預設 師 士；可加 合併）")
    ap.add_argument("--out", default=OUT_CSV)
    args = ap.parse_args()

    with open(SRC_JSON, encoding="utf-8") as f:
        data = json.load(f)
    with open(LEXICON, encoding="utf-8") as f:
        lex = json.load(f)

    rows = build_rows(data, lex, args.scopes)
    # utf-8-sig：Excel 直接開啟不亂碼
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"已輸出 {len(rows)} 列 × {len(HEADER)} 欄 → {os.path.relpath(args.out, ROOT)}")


if __name__ == "__main__":
    main()
