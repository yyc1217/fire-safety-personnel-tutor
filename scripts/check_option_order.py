#!/usr/bin/env python3
"""③ 選項順序全面比對 v3。

原理：原卷 PDF（Word 轉檔）之內部文件順序即邏輯閱讀順序；當年兩欄錯置係
pdftotext 版面重排所致。故取 PDF 文件順序文字流（正規化、剔除圈號/PUA 字元，
因舊年度卷圈號與選項首字順序顛倒），對每題：
1. 題幹錨點（多候選子串＋「選項A須隨後出現」驗證，防連鎖偏移）
2. 題目區間內取各選項全部出現位置，檢查可否挑出 A<B<C<D 遞增序列
   （容許選項互為前綴/重複值，取貪婪遞增指派）
不能遞增 → MISORDER（回報 PDF 實際順序）；找不到 → NOMATCH/NOANCHOR 人工覆核。

2026-07-04 全量掃描結果（issue #3 ③）：80 卷 3,200 題，MISORDER 0。
以下 7 筆為數學符號（√、^、上下標、≧）PDF 抽取瑕疵造成之殘留旗標，
已逐題人工目視原卷確認選項順序無誤，屬已知誤報：
  士/100/0907 Q31、士/104/0707 Q10、士/108/0907 Q6/Q29/Q31、
  士/108/0909 Q19、士/113/0807 Q17
"""
import glob, os, re, sys, unicodedata
import fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def norm(s):
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", "", s)
    for a, b in [("（", "("), ("）", ")"), ("：", ":"), ("；", ";"), ("，", ","),
                 ("。", "."), ("、", ","), ("．", "."), ("〜", "~"), ("–", "-"),
                 ("—", "-"), ("−", "-"), ("？", "?"), ("！", "!"), ("˙", "."),
                 ("‧", "."), ("・", "."), ("·", "."), ("ᐟ", "/")]:
        s = s.replace(a, b)
    s = re.sub(r"[()/⁄'’′`]", "", s)          # 排版性字元
    s = re.sub(r"[-①-⑳㈠-㈩]", "", s)  # 圈號/PUA
    return s

def parse_md(md_path):
    txt = open(md_path, encoding="utf-8").read()
    m = re.search(r"原卷：`(pdf/[^`]+?\.pdf)`", txt)
    pdf_rel = m.group(1) if m else None
    qs = []
    blocks = re.split(r"^### 第 (\d+) 題\s*$", txt, flags=re.M)
    for i in range(1, len(blocks), 2):
        qno = int(blocks[i]); body = blocks[i + 1]
        stem_lines, opts = [], []
        for line in body.splitlines():
            mo = re.match(r"- \(([A-D])\)\s*(.*)", line)
            if mo:
                opts.append(mo.group(2).strip())
                continue
            if line.startswith("**標準答案") or line.startswith("> 🏷️"):
                break
            if line.startswith(">") or line.startswith("!["):
                continue
            if line.strip():
                stem_lines.append(line.strip())
        qs.append({"no": qno, "stem": " ".join(stem_lines), "opts": opts})
    return pdf_rel, qs

def stem_candidates(stem_n, qno):
    """候選錨點：題號+前綴最強（許多題幹以相同法規名起頭，純前綴無鑑別度）。"""
    L = len(stem_n)
    c = []
    if L:
        c.append(f"{qno}{stem_n[:min(L, 12)]}")
    if L >= 24:
        c.append(stem_n[:24])
    if L >= 14:
        c += [stem_n[:14], stem_n[7:21] if L >= 28 else None, stem_n[-14:]]
    elif L:
        c.append(stem_n)
    return [x for x in c if x]

def find_anchor(stream, stem_n, opta_n, start, qno):
    """回傳 (錨點起點, 選項搜尋起點) 或 None。要求 optA 於錨點後視窗內出現。"""
    probe = opta_n[:8] if opta_n else ""
    for cand in stem_candidates(stem_n, qno):
        i = start
        for _ in range(6):  # 最多試 6 個出現點
            j = stream.find(cand, i)
            if j < 0:
                break
            win_end = j + len(cand) + max(len(stem_n), 60) + 400
            if not probe or stream.find(probe, j + len(cand), win_end) >= 0:
                return j, j + len(cand)
            i = j + 1
    return None

def occurrences(stream, s, lo, hi):
    out, i = [], lo
    while True:
        j = stream.find(s, i, hi)
        if j < 0:
            return out
        out.append(j); i = j + 1

def option_hits(stream, opt_n, lo, hi):
    s = opt_n
    while s and len(s) >= 3:
        hits = occurrences(stream, s, lo, hi)
        if hits:
            return hits
        ns = s[: int(len(s) * 0.7)]
        s = ns if len(ns) >= 3 else ""
    if opt_n and len(opt_n) < 3:
        return occurrences(stream, opt_n, lo, hi)
    return []

def increasing_pick(sets_):
    picked, cur = [], -1
    for st in sets_:
        nxt = [p for p in sorted(st) if p > cur]
        if not nxt:
            return None
        cur = nxt[0]; picked.append(cur)
    return picked

def check_exam(md_path):
    pdf_rel, qs = parse_md(md_path)
    pdf_path = os.path.join(ROOT, "corpus", pdf_rel) if pdf_rel else None
    if not pdf_path or not os.path.exists(pdf_path):
        # 師卷表頭僅寫檔名：以 md 路徑推導對應 pdf
        cand = md_path.replace("/md/", "/pdf/")[:-3] + ".pdf"
        if os.path.exists(cand):
            pdf_path = cand
        else:
            return [("NOPDF", md_path, None, pdf_rel or "原卷路徑未解析")]
    doc = fitz.open(pdf_path)
    stream = norm("".join(p.get_text() for p in doc))
    results = []
    anchors = {}
    cursor = 0
    for q in qs:
        opta = norm(q["opts"][0]) if q["opts"] else ""
        a = find_anchor(stream, norm(q["stem"]), opta, cursor, q["no"])
        anchors[q["no"]] = a
        if a:
            cursor = a[1]
    nos = [q["no"] for q in qs]
    for idx, q in enumerate(qs):
        if any("![" in o for o in q["opts"]) or len(q["opts"]) != 4:
            results.append(("SKIP", md_path, q["no"], "圖形選項或非四選項"))
            continue
        a = anchors[q["no"]]
        if not a:
            results.append(("NOANCHOR", md_path, q["no"], q["stem"][:30]))
            continue
        lo = a[1]
        hi = len(stream)
        for nxt in nos[idx + 1:]:
            if anchors.get(nxt):
                hi = anchors[nxt][0]
                break
        opts_n = [norm(o) for o in q["opts"]]
        hits = [option_hits(stream, o, lo, hi) for o in opts_n]
        missing = [l for l, h in zip("ABCD", hits) if not h]
        if missing:
            results.append(("NOMATCH", md_path, q["no"], "缺" + ",".join(missing)))
            continue
        if increasing_pick(hits):
            results.append(("OK", md_path, q["no"], ""))
        else:
            firsts = {l: min(h) for l, h in zip("ABCD", hits)}
            order = "".join(sorted(firsts, key=lambda k: firsts[k]))
            results.append(("MISORDER", md_path, q["no"], f"PDF實際順序≈{order}"))
    return results

def main(paths):
    tally = {}
    bad = []
    for pth in paths:
        for r in check_exam(pth):
            tally[r[0]] = tally.get(r[0], 0) + 1
            if r[0] not in ("OK", "SKIP"):
                bad.append(r)
    print("統計:", tally)
    for st, path, qno, info in bad:
        print(f"{st}\t{os.path.relpath(path, ROOT)}\tQ{qno}\t{info}")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        args = sorted(glob.glob(f"{ROOT}/corpus/md/士/*/*.md")) + \
               sorted(glob.glob(f"{ROOT}/corpus/md/師/*/*.md"))
        args = [a for a in args if "### 第 1 題" in open(a).read()]
    main(args)
