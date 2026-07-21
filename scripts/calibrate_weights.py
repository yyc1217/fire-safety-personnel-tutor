#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校準猜題法條加權頻率之衰減係數 r 與統計窗口 W。

對應 docs/設計_猜題權重與複習模式.md「四、實作狀態」第四項：
「待 statutes/ 法條 md 齊全後實測權重，校準衰減係數 r 與統計窗口」。

方法（時序回測 back-test）：
  猜題公式為 S(g)=Σ_y n(g,y)·r^(Y_now−y)，P(g)=S(g)/ΣS。
  對每個候選 (r, W)，以「用 ≤Y−1 年資料預測第 Y 年法條分布」的方式回測：
    - 訓練分數 S(g;Y,r,W)=Σ_{Y−W ≤ y ≤ Y−1} n(g,y)·r^((Y−1)−y)
    - 預測機率 P_pred(g)=平滑後正規化
    - 真值 A(g)=n(g,Y)/Σ_g n(g,Y)
  以兩個指標評分並跨測試年平均：
    1. 每題對數損失（log-loss / 交叉熵，proper scoring rule，越低越好）
    2. Spearman 等級相關（預測排名 vs 實際排名，越高越好）
  另附 baseline：純總次數（r=1、全窗）與純最近一年。

輸出純統計，不改任何法規/題庫檔。
"""
import json
import math
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "corpus")
TAGS = os.path.join(CORPUS, "tags_index.json")
INDEX = os.path.join(CORPUS, "index.json")


def load_code2subject():
    """科目代碼 → (等別, 正式科目名)。

    科目代碼逐年重編（同一科目跨年有多組代碼，如師消防法規＝0702/0802/0902），
    故以 index.json 之 name 欄位為正規化鍵，跨年併為同一卷別。
    """
    idx = json.load(open(INDEX, encoding="utf-8"))
    return {p["subject"]: (p["level"], p["name"]) for p in idx["papers"]}


CODE2SUB = load_code2subject()


def load_counts(dim="by_law", min_total=0, scope=None):
    """回傳 counts[key][year]=次數、key 集合、年份排序清單。

    dim: "by_law"（法規層級）或 "by_article"（條文層級）。
    min_total: 僅保留總出題數 >= 此門檻之 key（條文層級用以濾除單題雜訊）。
    scope: None=全部合併；(等別, 科目名) tuple=僅計該卷別（等級×科目）之題目。
    """
    data = json.load(open(TAGS, encoding="utf-8"))
    src = data[dim]
    counts = defaultdict(lambda: defaultdict(int))
    years = set()
    for key, qids in src.items():
        if len(qids) < min_total:
            continue
        for qid in qids:
            # qid 形如 "士/100/0908#Q4" → 等別/年/科目代碼#題號
            parts = qid.split("/")
            y = int(parts[1])
            if scope is not None:
                code = parts[2].split("#")[0]
                if CODE2SUB.get(code) != scope:
                    continue
            counts[key][y] += 1
            years.add(y)
    return counts, sorted(counts.keys()), sorted(years)


def list_subjects(dim="by_law", min_tags=1):
    """列出（等別, 科目名）卷別及其法規標記總數，依標記數由多至少。

    僅回傳法規標記數 >= min_tags 之卷別（火災學類無法規標記，自動排除）。
    """
    data = json.load(open(TAGS, encoding="utf-8"))
    tally = defaultdict(int)
    for key, qids in data[dim].items():
        for qid in qids:
            code = qid.split("/")[2].split("#")[0]
            sub = CODE2SUB.get(code)
            if sub:
                tally[sub] += 1
    subs = [(s, n) for s, n in tally.items() if n >= min_tags]
    return sorted(subs, key=lambda x: -x[1])


def predict(counts, laws, target_year, r, window):
    """用 [target_year-window, target_year-1] 年資料，算各法規預測分數。"""
    ref = target_year - 1  # Y_now = 最新可用年
    scores = {}
    for g in laws:
        s = 0.0
        for y, n in counts[g].items():
            if target_year - window <= y <= target_year - 1:
                s += n * (r ** (ref - y))
        scores[g] = s
    return scores


def normalize_smoothed(scores, laws, alpha=0.5):
    """加性平滑後正規化為機率（避免 log(0)）。"""
    total = sum(scores.get(g, 0.0) for g in laws) + alpha * len(laws)
    return {g: (scores.get(g, 0.0) + alpha) / total for g in laws}


def actual_dist(counts, laws, year):
    tot = sum(counts[g].get(year, 0) for g in laws)
    if tot == 0:
        return None, 0
    return {g: counts[g].get(year, 0) for g in laws}, tot


def spearman(pred_prob, actual_counts, laws):
    """預測機率排名 vs 實際次數排名之等級相關。"""
    def ranks(values):
        order = sorted(laws, key=lambda g: values[g])
        r = {}
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rp = ranks(pred_prob)
    ra = ranks({g: actual_counts[g] for g in laws})
    n = len(laws)
    d2 = sum((rp[g] - ra[g]) ** 2 for g in laws)
    return 1 - 6 * d2 / (n * (n * n - 1))


def backtest(counts, laws, years, r, window, test_years):
    logloss_sum = 0.0
    q_total = 0
    sp_list = []
    for Y in test_years:
        act, tot = actual_dist(counts, laws, Y)
        if act is None:
            continue
        scores = predict(counts, laws, Y, r, window)
        pred = normalize_smoothed(scores, laws)
        for g in laws:
            n = act[g]
            if n:
                logloss_sum += -n * math.log(pred[g])
        q_total += tot
        sp_list.append(spearman(pred, act, laws))
    avg_logloss = logloss_sum / q_total if q_total else float("nan")
    avg_sp = sum(sp_list) / len(sp_list) if sp_list else float("nan")
    return avg_logloss, avg_sp, q_total


R_GRID = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
W_GRID = [5, 7, 10, 13, 16]


def run_level(title, counts, keys, years):
    ymin = years[0]
    # 測試年：保留足夠歷史（至少 5 年）以比較窗口
    test_years = [y for y in years if y - ymin >= 5]
    print(f"## {title}")
    print(f"key 數 {len(keys)}；測試年 {test_years[0]}–{test_years[-1]}\n")
    print("每格：log-loss（↓越低越好）/ Spearman（↑越高越好）\n")
    header = "| r＼W |" + "".join(f" W={w} |" for w in W_GRID)
    print(header)
    print("|---|" + "".join("---|" for _ in W_GRID))
    results = {}
    for r in R_GRID:
        row = f"| **r={r}** |"
        for w in W_GRID:
            ll, sp, _ = backtest(counts, keys, years, r, w, test_years)
            results[(r, w)] = (ll, sp)
            row += f" {ll:.3f}/{sp:.3f} |"
        print(row)
    best = min(results, key=lambda k: results[k][0])
    best_sp = max(results, key=lambda k: results[k][1])
    ll_cnt, sp_cnt, _ = backtest(counts, keys, years, 1.0, 16, test_years)
    ll_last, sp_last, _ = backtest(counts, keys, years, 1e-9, 1, test_years)
    print(f"\n- **最低 log-loss**：r={best[0]}, W={best[1]} → "
          f"{results[best][0]:.3f}（Spearman {results[best][1]:.3f}）")
    print(f"- **最高 Spearman**：r={best_sp[0]}, W={best_sp[1]} → "
          f"{results[best_sp][1]:.3f}（log-loss {results[best_sp][0]:.3f}）")
    print(f"- baseline 純總次數（r=1,全窗）：{ll_cnt:.3f} / {sp_cnt:.3f}")
    print(f"- baseline 純最近一年（W=1）：{ll_last:.3f} / {sp_last:.3f}\n")
    return results


def show_examples(r=0.8, window=10, topn=5):
    """列出「校準 vs 純總次數」名次差最大之法規，供設計文件第五節實例對比。

    用截至最新年（Y_now）之資料預測次年，比較兩種排序：
      - 校準：S(g)=Σ n(g,y)·r^(Y_now−y)，限窗 [Y_now−window+1, Y_now]
      - 純總次數：Σ n(g,y)（全窗）
    """
    counts, laws, years = load_counts("by_law")
    ynow = years[-1]

    def cal_score(g):
        return sum(n * (r ** (ynow - y)) for y, n in counts[g].items()
                   if ynow - window + 1 <= y <= ynow)

    def cnt_score(g):
        return sum(counts[g].values())

    def rank_map(fn):
        return {g: i + 1 for i, g in enumerate(sorted(laws, key=fn, reverse=True))}

    r_cal, r_cnt = rank_map(cal_score), rank_map(cnt_score)

    def recent(g, k):
        return sum(n for y, n in counts[g].items() if ynow - k + 1 <= y <= ynow)

    def early(g, cut=107):
        return sum(n for y, n in counts[g].items() if y <= cut)

    # 依「純總次數名次 − 校準名次」排序：負=校準降權、正=校準升權
    delta = sorted(laws, key=lambda g: r_cnt[g] - r_cal[g])
    print(f"# 校準實例：截至 {ynow} 年資料預測 {ynow + 1} 年（r={r}, 窗口={window}）\n")
    print("欄位：法規 | 總次數 | 近3年 | ≤107年 | 純總次數名次 → 校準名次\n")
    print("## 舊年代熱、近年冷 → 校準降權（名次下降）")
    for g in delta[:topn]:
        print(f"- {g}：總{cnt_score(g)} 近3年{recent(g,3)} ≤107年{early(g)} | "
              f"第{r_cnt[g]} → 第{r_cal[g]}")
    print("\n## 新興／近年才冒出 → 校準升權（名次上升）")
    for g in delta[-topn:][::-1]:
        print(f"- {g}：總{cnt_score(g)} 近3年{recent(g,3)} ≤107年{early(g)} | "
              f"第{r_cnt[g]} → 第{r_cal[g]}")


def load_subject_datasets(dim="by_law", min_tags=30):
    """回傳 [(subject, counts, keys, years), ...]，每卷別獨立之法規年次數。

    min_tags：法規標記數過少之卷別（如師各設備科 <100）樣本稀疏、回測雜訊大，
    仍納入但於報表標注；此門檻僅排除幾乎無法規題之卷別。
    """
    datasets = []
    for sub, n in list_subjects(dim, min_tags=min_tags):
        counts, keys, years = load_counts(dim, scope=sub)
        datasets.append((sub, counts, keys, years, n))
    return datasets


def backtest_pooled(datasets, r, window):
    """全卷別集約回測：各卷別於自身法規詞彙內預測，log-loss 併總、Spearman 取平均。

    「分卷別」方法之整體評分——用來挑一組全域 (r, W) 供各卷別共用。
    """
    logloss_sum = 0.0
    q_total = 0
    sp_list = []
    for sub, counts, keys, years, _ in datasets:
        ymin = years[0]
        test_years = [y for y in years if y - ymin >= 5]
        for Y in test_years:
            act, tot = actual_dist(counts, keys, Y)
            if act is None:
                continue
            pred = normalize_smoothed(predict(counts, keys, Y, r, window), keys)
            for g in keys:
                if act[g]:
                    logloss_sum += -act[g] * math.log(pred[g])
            q_total += tot
            if len(keys) > 2:
                sp_list.append(spearman(pred, act, keys))
    ll = logloss_sum / q_total if q_total else float("nan")
    sp = sum(sp_list) / len(sp_list) if sp_list else float("nan")
    return ll, sp, q_total


def run_split_calibration():
    """分等級×科目（卷別）之校準：集約網格 + 各卷別最佳 + 與合併對照。"""
    datasets = load_subject_datasets("by_law", min_tags=30)
    print("## 分等級×科目（卷別）校準\n")
    print(f"納入卷別 {len(datasets)} 個（法規標記數≥30；火災學類無法規題已排除）；"
          "各卷別於自身題目與法規詞彙內獨立回測，測試年 105–115。\n")

    print("### 集約網格（各卷別 log-loss 併總 / Spearman 平均）\n")
    header = "| r＼W |" + "".join(f" W={w} |" for w in W_GRID)
    print(header + "\n|---|" + "".join("---|" for _ in W_GRID))
    results = {}
    for r in R_GRID:
        row = f"| **r={r}** |"
        for w in W_GRID:
            ll, sp, _ = backtest_pooled(datasets, r, w)
            results[(r, w)] = (ll, sp)
            row += f" {ll:.3f}/{sp:.3f} |"
        print(row)
    best = min(results, key=lambda k: results[k][0])
    ll_cnt, sp_cnt, _ = backtest_pooled(datasets, 1.0, 16)
    ll_last, sp_last, _ = backtest_pooled(datasets, 1e-9, 1)
    print(f"\n- **集約最低 log-loss**：r={best[0]}, W={best[1]} → "
          f"{results[best][0]:.3f}（Spearman {results[best][1]:.3f}）")
    print(f"- baseline 純總次數（r=1,全窗）：{ll_cnt:.3f} / {sp_cnt:.3f}")
    print(f"- baseline 純最近一年（W=1）：{ll_last:.3f} / {sp_last:.3f}")

    print("\n### 各卷別獨立最佳（log-loss）與樣本量\n")
    print("| 卷別 | 法規標記數 | 不同法規 | 卷別最佳(r,W) | log-loss |")
    print("|---|:--:|:--:|:--:|:--:|")
    for sub, counts, keys, years, n in datasets:
        ymin = years[0]
        ty = [y for y in years if y - ymin >= 5]
        rr = {}
        for r in R_GRID:
            for w in W_GRID:
                ll, _, _ = backtest(counts, keys, years, r, w, ty)
                rr[(r, w)] = ll
        b = min(rr, key=lambda k: rr[k])
        print(f"| {sub[0]} {sub[1]} | {n} | {len(keys)} | r={b[0]}, W={b[1]} | {rr[b]:.3f} |")

    print(f"\n> 註：集約最佳 (r={best[0]}, W={best[1]}) 為各卷別共用之建議值；"
          "個別卷別最佳因樣本稀疏而漂動（尤師各設備科），不宜逐卷各取一組，"
          "故以集約值為準、僅供參考各卷別差異。\n")
    return best


def show_examples_split(r=0.8, window=10):
    """對照同一法規在「師消防法規」vs「士消防法規概要」之加權名次，
    說明分等級×科目之必要性（同法規因卷別而比重不同）。供設計文件第五節。"""
    def ranked(scope):
        counts, keys, years = load_counts("by_law", scope=scope)
        ynow = years[-1]
        sc = {g: sum(n * (r ** (ynow - y)) for y, n in counts[g].items()
                     if ynow - window + 1 <= y <= ynow) for g in keys}
        rk = {g: i + 1 for i, g in enumerate(sorted(keys, key=lambda x: sc[x],
                                                     reverse=True))}
        tot = {g: sum(counts[g].values()) for g in keys}
        return rk, tot

    rs, ts = ranked(("師", "消防法規"))
    ri, ti = ranked(("士", "消防法規概要"))
    laws = ["各類場所消防安全設備設置標準",
            "公共危險物品及可燃性高壓氣體製造儲存處理場所設置標準暨安全管理辦法",
            "消防法", "建築技術規則建築設計施工編", "消防設備人員法",
            "消防法施行細則", "防焰性能認證實施辦法"]
    print(f"# 卷別實例：同法規於師 vs 士之加權名次（r={r}, 窗口={window}，"
          f"截至 115 年預測 116 年）\n")
    print("法規 | 師消防法規 名次(總次數) | 士消防法規概要 名次(總次數)")
    for g in laws:
        s = f"第{rs[g]}（{ts.get(g,0)}）" if g in rs else "—"
        i = f"第{ri[g]}（{ti.get(g,0)}）" if g in ri else "—"
        print(f"- {g}：師 {s} ｜ 士 {i}")


def main():
    print("# 猜題法條加權頻率校準（時序 back-test）\n")
    print("公式 S(g)=Σ_y n(g,y)·r^(Y_now−y)，以「≤Y−1 年資料預測第 Y 年分布」回測。")
    print("log-loss=每題交叉熵（proper scoring rule）；Spearman=排名相關；平滑 alpha=0.5。\n")

    print("# 甲、分等級×科目（卷別）——實際採用之計算粒度\n")
    run_split_calibration()

    print("\n# 乙、全部合併（對照基準，非實際採用）\n")
    c1, k1, y1 = load_counts("by_law")
    run_level("法規層級（by_law，合併）", c1, k1, y1)
    # 條文層級：濾除總數 <5 之單題雜訊，聚焦可辨識條號之常考條文
    c2, k2, y2 = load_counts("by_article", min_total=5)
    run_level("條文層級（by_article，總數≥5，合併）", c2, k2, y2)


if __name__ == "__main__":
    import sys
    if "--examples-split" in sys.argv:
        show_examples_split()
    elif "--examples" in sys.argv:
        show_examples()
    else:
        main()
