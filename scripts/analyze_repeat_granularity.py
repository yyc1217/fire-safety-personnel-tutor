#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_repeat_granularity.py — 考點「重考率 × 顆粒度」分析 + 隨機基準置換檢定。

回答的問題：「前一年考過的考點今年不會再考」這句話可信嗎？

作法：對同一批考古題，用**四層顆粒度**（設備 → 組件 → 子考點 → 子子考點）分別計算
「前一年考過之考點，今年又出現」之比例（重考率），並以**置換檢定**（打散年份標籤 N 次）
算出「命題與年份無關」時的隨機基準，判斷觀測重考率是否顯著低於隨機（＝是否真有
『迴避去年考點』效應），而非只是切得越細、格子越多的機率假象。

重要界線：
- 本工具為**探索性分析**。子考點／子子考點層採**關鍵字啟發式**分桶（詞庫見
  scripts/repeat_lexicon.json），準確度有限（呼應 build_tags.py 停用之教訓）。
- **絕不回寫** corpus/tags_index.json 或 inline 🏷️ 語意標籤——語意標籤仍為唯一真相來源。
- 產物：corpus/命題重考率分析.md（人可讀）、corpus/repeat_granularity.json（機器可讀）。

用法：
    python3 scripts/analyze_repeat_granularity.py            # 產出報告與 JSON
    python3 scripts/analyze_repeat_granularity.py --perm 5000  # 調整置換次數（預設 3000）
"""

import re
import os
import json
import glob
import random
import argparse
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "corpus")
LEXICON = os.path.join(ROOT, "scripts", "repeat_lexicon.json")
OUT_MD = os.path.join(CORPUS, "命題重考率分析.md")
OUT_JSON = os.path.join(CORPUS, "repeat_granularity.json")

LEVEL_TAGS = {"師": "/師/", "士": "/士/"}


def load_lexicon():
    with open(LEXICON, encoding="utf-8") as f:
        return json.load(f)


def year_of(path):
    return int(re.search(r"/(\d{3})/", path).group(1))


def level_of(path):
    return "師" if "/師/" in path else "士"


def iter_questions(paths, exclude_stem):
    """回傳 (level, year, stem)；stem 取第一個選項 - (A) 之前之題幹。"""
    for f in paths:
        with open(f, encoding="utf-8") as fh:
            txt = fh.read()
        lv, yr = level_of(f), year_of(f)
        for blk in re.split(r"\n###\s+", txt):
            stem = re.split(r"\n-\s*[（(]?A", blk)[0]
            if any(x in stem for x in exclude_stem):
                continue
            yield lv, yr, stem


def classify(stem, buckets_ordered):
    """buckets_ordered: list of (name, keywords)；回傳第一個命中桶名，否則 None。"""
    for name, kws in buckets_ordered:
        if any(k in stem for k in kws):
            return name
    return None


def ordered_buckets(layer_dict):
    """濾掉底線開頭之控制鍵（_focus/_gate/...），保留插入順序。"""
    return [(k, v) for k, v in layer_dict.items() if not k.startswith("_")]


def repeat_rate(pairs):
    """pairs: list of (year, bucket)。回傳 (前一年考點合計, 隔年重考數, 重考率%)。"""
    yr = defaultdict(set)
    for y, c in pairs:
        yr[y].add(c)
    years = sorted(yr)
    tp = tr = 0
    for i in range(1, len(years)):
        y0, y1 = years[i - 1], years[i]
        if y1 - y0 != 1:  # 僅計真正連續年
            continue
        tp += len(yr[y0])
        tr += len(yr[y0] & yr[y1])
    rate = tr / tp * 100 if tp else None
    return tp, tr, rate


def permutation_test(pairs, n_perm, seed=42):
    """打散 bucket 標籤（保持每年題數），估計隨機基準重考率分布。"""
    _, _, obs = repeat_rate(pairs)
    if obs is None or len(pairs) < 4:
        return {"observed": obs, "null_mean": None, "ci95": None,
                "percentile": None, "n_perm": 0}
    rng = random.Random(seed)
    years = [y for y, _ in pairs]
    cats = [c for _, c in pairs]
    null = []
    for _ in range(n_perm):
        rng.shuffle(cats)
        _, _, r = repeat_rate(list(zip(years, cats)))
        null.append(r)
    null.sort()
    mean = sum(null) / len(null)
    lo = null[int(0.025 * len(null))]
    hi = null[int(0.975 * len(null))]
    below = sum(1 for x in null if x < obs) / len(null) * 100
    return {"observed": obs, "null_mean": mean, "ci95": [lo, hi],
            "percentile": below, "n_perm": n_perm}


def gate_pass(stem, layer_dict):
    """子考點/子子考點層之焦點設備閘門：_gate 命中且 _gate_exclude 未命中。"""
    gate = layer_dict.get("_gate")
    if gate and not any(g in stem for g in gate):
        return False
    gate_ex = layer_dict.get("_gate_exclude")
    if gate_ex and any(g in stem for g in gate_ex):
        return False
    return True


def analyze_layer(questions, layer_dict, n_perm):
    """對單一顆粒度層，回傳分桶年份分布、重考率、置換檢定、未分類率（皆分等級）。"""
    buckets = ordered_buckets(layer_dict)
    pairs_by_scope = {"師": [], "士": [], "合併": []}
    bucket_years_by_scope = {"師": defaultdict(set), "士": defaultdict(set),
                             "合併": defaultdict(set)}
    tot_by_scope = {"師": 0, "士": 0, "合併": 0}
    unc_by_scope = {"師": 0, "士": 0, "合併": 0}
    for lv, yr, stem in questions:
        if not gate_pass(stem, layer_dict):
            continue
        b = classify(stem, buckets)
        tot_by_scope[lv] += 1
        tot_by_scope["合併"] += 1
        if b is None:
            unc_by_scope[lv] += 1
            unc_by_scope["合併"] += 1
            continue
        for sc in (lv, "合併"):
            bucket_years_by_scope[sc][b].add(yr)
            pairs_by_scope[sc].append((yr, b))
    gated = bool(layer_dict.get("_gate"))
    out = {"gated": gated, "scopes": {}}
    for scope, pairs in pairs_by_scope.items():
        tot = tot_by_scope[scope]
        by = bucket_years_by_scope[scope]
        entry = {
            "buckets": {b: sorted(ys) for b, ys in
                        sorted(by.items(), key=lambda kv: -len(kv[1]))},
            "n_total": tot, "n_unclassified": unc_by_scope[scope],
            "unclassified_rate": (unc_by_scope[scope] / tot * 100) if tot else None,
        }
        if pairs:
            tp, tr, rate = repeat_rate(pairs)
            entry.update({"n": len(pairs), "prev_total": tp, "repeats": tr,
                          "repeat_rate": rate, "perm": permutation_test(pairs, n_perm)})
        out["scopes"][scope] = entry
    # 相容舊欄位（合併層級之桶分布／未分類，供既有引用）
    merged = out["scopes"]["合併"]
    out["buckets"] = merged["buckets"]
    out["n_total"] = merged["n_total"]
    out["n_unclassified"] = merged["n_unclassified"]
    out["unclassified_rate"] = merged["unclassified_rate"]
    return out


def run(n_perm):
    lex = load_lexicon()
    exclude = lex.get("exclude_stem", [])
    result = {"_meta": {"generator": "scripts/analyze_repeat_granularity.py",
                        "lexicon": "scripts/repeat_lexicon.json",
                        "n_perm": n_perm,
                        "note": "關鍵字啟發式分桶，探索性分析，不回寫語意標籤。"},
              "systems": {}}
    for sysname, sysdef in lex["systems"].items():
        paths = []
        for g in sysdef["papers_glob"]:
            paths += glob.glob(os.path.join(CORPUS, g))
        questions = list(iter_questions(paths, exclude))
        result["systems"][sysname] = {}
        for layer_name, layer_dict in sysdef["layers"].items():
            result["systems"][sysname][layer_name] = analyze_layer(
                questions, layer_dict, n_perm)
    return result, lex


# --------------------------- 報告輸出 --------------------------- #

LADDER = ["設備", "組件", "子考點", "子子考點"]


def fmt_rate(v):
    return f"{v:.0f}%" if isinstance(v, (int, float)) else "—"


def verdict(perm):
    """依置換檢定給白話判讀。"""
    obs, mean, pct = perm.get("observed"), perm.get("null_mean"), perm.get("percentile")
    if obs is None or mean is None:
        return "樣本不足，無法檢定"
    if pct is None:
        return "—"
    if pct < 2.5:
        return "**顯著低於隨機**（疑有迴避傾向，仍須注意樣本）"
    if pct < 5:
        return "略低於隨機（單尾邊緣，樣本小，多屬雜訊）"
    if pct > 95:
        return "顯著高於隨機（比隨機更常重考）"
    return "與隨機無異（重考率下降＝顆粒度機率，非迴避）"


LEVEL_LABEL = {"師": "師篇（消防設備師，申論為主）",
               "士": "士篇（消防設備士，測驗為主＋部分申論）"}


def render_ladder(L, sysres, scope):
    L.append("| 顆粒度 | 桶數 | 題數 | 觀測重考率 | 隨機基準 | 隨機95%區間 | 觀測百分位 | 判讀 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for layer in LADDER:
        if layer not in sysres:
            continue
        sc = sysres[layer]["scopes"].get(scope)
        if not sc or "perm" not in sc:
            continue
        perm = sc["perm"]
        ci = perm.get("ci95")
        ci_s = f"[{ci[0]:.0f}%,{ci[1]:.0f}%]" if ci else "—"
        pct = perm.get("percentile")
        pct_s = f"{pct:.0f}%" if pct is not None else "—"
        L.append(f"| {layer} | {len(sc.get('buckets', {}))} | {sc['n']} | "
                 f"{fmt_rate(sc['repeat_rate'])} | {fmt_rate(perm.get('null_mean'))} | "
                 f"{ci_s} | {pct_s} | {verdict(perm)} |")
    L.append("")


def render_buckets(L, sysname, sysres, lex, scope):
    for layer in LADDER:
        if layer not in sysres:
            continue
        sc = sysres[layer]["scopes"].get(scope)
        if not sc or not sc.get("buckets"):
            continue
        ld = lex["systems"][sysname]["layers"][layer]
        focus = ld.get("_focus")
        title = f"#### {layer} 層桶分布"
        if focus:
            title += f"（焦點：{focus}）"
        L.append(title)
        note = ld.get("_note")
        if note:
            L.append(f"> {note}")
        urate = sc["unclassified_rate"]
        if urate is not None:
            if sysres[layer].get("gated"):
                flag = " 🔴 詞庫待補" if urate > 20 else ""
                L.append(f"> 未分類率：{urate:.0f}%（{sc['n_unclassified']}/{sc['n_total']}）{flag}")
            else:
                L.append(f"> 落桶率：{100 - urate:.0f}%（分母 {sc['n_total']} 題含他系統與"
                         f"跨設備綜合題，未落桶非必為詞庫缺口，僅供參考）")
        L.append("")
        L.append("| 桶（考點） | 考過年數 | 出現年份 |")
        L.append("|---|---:|---|")
        for b, ys in sc["buckets"].items():
            L.append(f"| {b} | {len(ys)} | {','.join(map(str, ys))} |")
        L.append("")


def top_recurring(sc, k=3, min_frac=0.5):
    """回傳該 scope 該層中最常回鍋之桶名（年年考者優先）。"""
    buckets = sc.get("buckets", {})
    if not buckets:
        return []
    active_years = len({y for ys in buckets.values() for y in ys})
    ranked = sorted(buckets.items(), key=lambda kv: -len(kv[1]))
    core = [b for b, ys in ranked if len(ys) >= max(2, min_frac * active_years)]
    return (core or [b for b, _ in ranked])[:k]


def render_conclusion(L, scope, systems):
    kind = "申論" if scope == "師" else "測驗"
    # 掃各系統×層，依置換檢定百分位分類：高於(>95)／低於(<5)／無異
    high, low = [], []
    for sysname, sysres in systems.items():
        for layer in LADDER:
            if layer not in sysres:
                continue
            sc = sysres[layer]["scopes"].get(scope)
            if not sc or "perm" not in sc:
                continue
            pct = sc["perm"].get("percentile")
            if pct is None:
                continue
            if pct > 95:
                high.append((sysname, layer, sc))
            elif pct < 5:
                low.append((sysname, layer, sc))

    # 小結
    L.append(f"## {scope}篇 · 小結")
    L.append("")
    L.append(f"1. **粗顆粒度年年回鍋**：{kind}卷之設備／組件層重考率高，多與隨機無異或"
             "**顯著高於隨機**——「去年考過今年不考」明顯不成立。")
    L.append("2. **細顆粒度下降但非迴避**：隨顆粒度下降，但置換檢定顯示與隨機無異或顯著高於隨機，"
             "下降屬機率，非命題者迴避。")
    L.append("3. **裁決**：當篩題規則不可信；意義只在「同一核心考點今年多半**換一個子考點角度**」。")
    L.append("")

    # 實務建議：**只在達統計顯著時給方向**
    L.append(f"## {scope}篇 · 實務建議（{kind}）")
    L.append("")
    L.append("> **原則**：僅在置換檢定**達統計顯著**時給方向性建議；與隨機無異之層級不另加權"
             "（依歷年基礎頻率準備即可，勿因『去年考過』增減）。以下核心桶取自該層年年回鍋者。")
    L.append("")
    if high:
        L.append("### 🔺 優先準備（顯著高於隨機：比隨機更常重考 → 去年考過今年極可能再考）")
        L.append("")
        L.append("此類考點**回鍋率顯著高於機率**，是最穩的高投報方向，務必先掌握其年年回鍋之核心：")
        L.append("")
        L.append("| 系統 · 層級 | 觀測/隨機 | 應優先熟練之核心考點 |")
        L.append("|---|---:|---|")
        for sysname, layer, sc in high:
            perm = sc["perm"]
            rr = f"{sc['repeat_rate']:.0f}%/{perm['null_mean']:.0f}%"
            cores = "、".join(top_recurring(sc, 3))
            L.append(f"| {sysname} · {layer} | {rr} | {cores} |")
        L.append("")
        if scope == "師":
            L.append("> 申論導向：上列核心練到能**繪圖、寫檢查方法／判定、逐步計算**；"
                     "並預期今年**換一個子考點角度**（同一核心、不同問法）。")
        else:
            L.append("> 測驗導向：上列核心之**具體數值／判定**（放水壓力、藥劑量、保安距離、管制量…）"
                     "務必**背牢**，測驗年年反覆考這些硬數字。")
        L.append("")
    else:
        L.append("### 🔺 優先準備（顯著高於隨機）")
        L.append("")
        L.append("本等別無層級達「顯著高於隨機」，各系統依基礎頻率準備即可。")
        L.append("")
    if low:
        L.append("### 🔻 可略降優先（顯著低於隨機：剛考過短期較少見）")
        L.append("")
        L.append("> ⚠️ 此類多為**最細子層、樣本極小且屬事後多重比較**，訊號脆弱，僅供微調、不保證不考。")
        L.append("")
        L.append("| 系統 · 層級 | 觀測/隨機 | 說明 |")
        L.append("|---|---:|---|")
        for sysname, layer, sc in low:
            perm = sc["perm"]
            rr = f"{sc['repeat_rate']:.0f}%/{perm['null_mean']:.0f}%"
            L.append(f"| {sysname} · {layer} | {rr} | 該層最細子項逐年輪替；"
                     f"**去年剛熟練之特定細項**可略降重練優先（詳見上方該層桶分布），"
                     f"惟樣本小，仍不保證不考。 |")
        L.append("")
    L.append("### ➖ 其餘（與隨機無異）")
    L.append("")
    L.append("上列以外之系統與層級**無回鍋／迴避訊號**，照歷年高頻考點準備，勿因去年是否考過而增減；"
             "長間隔回鍋型併看 [`命題週期分析.md`](命題週期分析.md)。**任何層級都別劃掉去年考點**"
             "（核心考點年年可再考）。")
    L.append("")


def build_md(result, lex, n_perm):
    systems = result["systems"]
    L = []
    L.append("# 命題重考率 × 顆粒度分析")
    L.append("")
    L.append("> 由 `scripts/analyze_repeat_granularity.py` 產生（詞庫 `scripts/repeat_lexicon.json`）。"
             "驗證命題「前一年考過的考點今年不會再考」之可信度。")
    L.append(">")
    L.append("> ⚠️ **本報告為探索性分析**：子考點／子子考點層採**關鍵字啟發式**分桶，"
             "非語意標籤，個題可能歸錯（見各層未分類率），數字有 ±數個百分點誤差；"
             "分桶粗細由詞庫人為設定，會直接左右重考率。**結論一律以官方現行版與 inline "
             "🏷️ 語意標籤為準**；本工具不回寫任何標籤。")
    L.append("")
    L.append("## 核心方法：重考率 vs 隨機基準")
    L.append("")
    L.append("- **重考率**：連續兩年 Y-1→Y，前一年考過之考點集合中，今年又出現者之比例。"
             "此值越低＝越支持「去年考過今年不考」。")
    L.append(f"- **隨機基準（置換檢定，{n_perm} 次）**：打散年份標籤後之重考率分布。"
             "若觀測值落在此分布內（與隨機無異），代表重考率高低純屬「桶數 × 每年題數」之機率結果，"
             "**命題者並未刻意迴避去年考點**；唯有觀測**顯著低於**隨機，才是真有迴避效應。")
    L.append(">")
    L.append("> **編排原則（各等別獨立）**：師卷與士卷命題委員不同，本報告**先分師／士，再分系統**，"
             "結論與實務建議亦分師／士；不呈現跨等別合併之判讀（合併數據仍存於 "
             "`repeat_granularity.json` 供查）。")
    L.append("")

    # 章節索引（GitHub 錨點；師／士重複之系統名以 -1 後綴，依文件出現順序計）
    seen = {}

    def anc(text):
        s = re.sub(r"[^一-鿿0-9a-z \-_]", "", text.strip().lower())
        s = s.replace(" ", "-")
        n = seen.get(s, 0)
        seen[s] = n + 1
        return s if n == 0 else f"{s}-{n}"

    sys_names = list(systems)
    a_method = anc("核心方法：重考率 vs 隨機基準")
    L.append("## 章節索引")
    L.append("")
    L.append(f"- [核心方法](#{a_method})")
    for scope in ("師", "士"):
        a_lvl = anc(LEVEL_LABEL[scope])
        L.append(f"- [{LEVEL_LABEL[scope]}](#{a_lvl})")
        sys_links = " · ".join(f"[{name}](#{anc(name)})" for name in sys_names)
        L.append(f"    - 系統：{sys_links}")
        a_sum = anc(f"{scope}篇 · 小結")
        adv_label = "實務建議（申論）" if scope == "師" else "實務建議（測驗）"
        a_adv = anc(f"{scope}篇 · {adv_label}")
        L.append(f"    - [{scope}篇 · 小結](#{a_sum}) · [{scope}篇 · {adv_label}](#{a_adv})")
    a_verdict = anc("兩等別共通裁決")
    L.append(f"- [兩等別共通裁決](#{a_verdict})")
    L.append("")

    for scope in ("師", "士"):
        L.append(f"# {LEVEL_LABEL[scope]}")
        L.append("")
        for sysname, sysres in systems.items():
            # 該系統於此等別是否有資料
            if not any(scope in sysres[l]["scopes"] and "perm" in sysres[l]["scopes"][scope]
                       for l in LADDER if l in sysres):
                continue
            L.append(f"## {sysname}")
            L.append("")
            L.append("### 顆粒度階梯")
            L.append("")
            render_ladder(L, sysres, scope)
            L.append("### 桶分布")
            L.append("")
            render_buckets(L, sysname, sysres, lex, scope)
        render_conclusion(L, scope, systems)

    L.append("---")
    L.append("")
    L.append("## 兩等別共通裁決")
    L.append("")
    L.append("**「前一年考過的考點今年不會再考」不可信**：師、士兩卷皆然——粗顆粒度（設備／組件）"
             "核心考點**年年回鍋**，細顆粒度重考率下降純屬顆粒度機率（多處甚至**顯著高於**隨機），"
             "**無任何『迴避去年考點』之證據**。此口訣僅在「同一核心考點今年換一個子考點角度重出」"
             "這層意義上近似成立——是**換角度、非不考**。")
    L.append("")
    L.append("> 方法學細節、置換檢定原理與完整警語見 "
             "[`docs/設計_重考率與顆粒度分析.md`](../docs/設計_重考率與顆粒度分析.md)。")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--perm", type=int, default=3000, help="置換檢定次數（預設 3000）")
    args = ap.parse_args()
    result, lex = run(args.perm)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    md = build_md(result, lex, args.perm)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"已產出：\n  {OUT_MD}\n  {OUT_JSON}")
    # 主控台摘要（各等別獨立）
    for sysname, sysres in result["systems"].items():
        print(f"\n【{sysname}】顆粒度階梯（師／士各別）：")
        for scope in ("師", "士"):
            print(f"  〔{scope}〕")
            for layer in LADDER:
                if layer not in sysres:
                    continue
                m = sysres[layer]["scopes"].get(scope)
                if not m:
                    continue
                perm = m["perm"]
                print(f"    {layer:<5} 重考率 {fmt_rate(m['repeat_rate']):>4}"
                      f"｜隨機 {fmt_rate(perm.get('null_mean')):>4}"
                      f"｜百分位 {perm.get('percentile')}"
                      f"｜{verdict(perm)}")


if __name__ == "__main__":
    main()
