#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_tables_extract.py — 以 pdfplumber 線框偵測還原法規 PDF 之表格結構，輸出 Markdown。

背景（issue #41）：`pdftotext -layout` 只擷取文字層，表格欄列結構全數遺失。
本腳本讀 PDF 繪線（ruling lines）重建儲存格網格：以各儲存格 bbox 求出列/欄邊界，
還原**跨欄（colspan）與跨列（rowspan）**語意（extract_table 之 None 無法區分兩者），
支援多層表頭與跨頁拼接（續頁重複表頭自動去除）。

三種輸出模式（依 CLAUDE.md「附表處理原則」）：
  grid  簡單網格 → Markdown pipe table（多層表頭合併為單列；縱向合併值逐列重複）
  tree  複雜跨欄表 → 逐列樹狀展開（每列一區塊：首欄為題、各欄「表頭：值」）
  form  檢修報告表／檢查表表單 → 檢修項目巢狀骨架（填寫欄省略），保留層級

用法：
  python3 scripts/pdf_tables_extract.py <pdf> --pages 278 --list
  python3 scripts/pdf_tables_extract.py <pdf> --pages 278 --table 1 --mode grid --header-rows 2
  python3 scripts/pdf_tables_extract.py <pdf> --pages 271-272 --mode tree --header-rows 3 --label-skip 1
  python3 scripts/pdf_tables_extract.py <pdf> --pages 18-19 --mode form

  --pages a-b      跨頁自動拼接
  --table N        只取範圍內第 N 個表格（0 起算；預設全取）
  --header-rows N  表頭列數（預設自動偵測）
  --label-skip N   建表頭標籤時略過最上層 N 列群組標題（如「適用之感熱式探測器」）
  --label-cols N   form 模式左側「項目層級」欄數（預設自動偵測）

輸出為草稿：合併儲存格語意（尤其備註／備考跨欄）仍須人工核對後才入庫。
"""
import argparse
import re
import sys
import unicodedata

try:
    import pdfplumber
except ImportError:
    sys.exit("需要 pdfplumber：pip install pdfplumber")

CJK = r"㐀-鿿豈-﫿　-〿＀-￯"


def clean(text):
    """相容表意字正規化＋去 CJK 排版空白＋換行摺疊。

    不做全面 NFKC（會把全形標點「，」「（」折成半形），僅正規化
    CJK 相容區（U+F900–FAFF，如 U+F97E→量）。
    """
    if text is None:
        return ""
    t = "".join(unicodedata.normalize("NFKC", ch)
                if "豈" <= ch <= "﫿" else ch for ch in text)
    t = t.replace("\n", " ")
    prev = None
    while prev != t:
        prev = t
        t = re.sub(rf"([{CJK}]) +(?=[{CJK}])", r"\1", t)
    t = re.sub(r" {2,}", " ", t)
    return t.strip()


# ---------- 跨欄跨列網格重建 ----------

def _cluster(vals, tol=2.0):
    vals = sorted(vals)
    groups = [[vals[0]]]
    for v in vals[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _nearest(edges, v):
    return min(range(len(edges)), key=lambda i: abs(edges[i] - v))


class Cell:
    __slots__ = ("text", "r0", "c0", "rs", "cs", "w")

    def __init__(self, text, r0, c0, rs, cs, w):
        self.text, self.r0, self.c0, self.rs, self.cs, self.w = text, r0, c0, rs, cs, w


def build_grid(tb, page):
    """由 Table 之儲存格 bbox 重建網格：grid[i][j] → Cell（跨距內共用同一 Cell）。"""
    xs = _cluster([v for c in tb.cells for v in (c[0], c[2])])
    ys = _cluster([v for c in tb.cells for v in (c[1], c[3])])
    nrows, ncols = len(ys) - 1, len(xs) - 1
    grid = [[None] * ncols for _ in range(nrows)]
    for (x0, top, x1, bottom) in tb.cells:
        c0, c1 = _nearest(xs, x0), _nearest(xs, x1)
        r0, r1 = _nearest(ys, top), _nearest(ys, bottom)
        if r1 <= r0 or c1 <= c0:
            continue
        text = clean(page.crop((x0, top, x1, bottom)).extract_text())
        cell = Cell(text, r0, c0, r1 - r0, c1 - c0, ncols)
        for r in range(r0, r1):
            for c in range(c0, c1):
                grid[r][c] = cell
    return grid


def stitch(grids):
    """跨頁拼接為列清單（每列＝Cell 清單，可能含 None）；續頁重複表頭去除。"""
    if not grids:
        return []
    rows = list(grids[0])

    def rowkey(row):
        return tuple((c.text if c else None) for c in row)

    head = [rowkey(r) for r in grids[0][: min(4, len(grids[0]))]]
    shifted = set()
    for g in grids[1:]:
        skip = 0
        while skip < len(g) and skip < len(head) and rowkey(g[skip]) == head[skip]:
            skip += 1
        offset = len(rows) - skip  # 續頁 Cell 之 r0 平移（每 Cell 僅一次）
        for r in g[skip:]:
            for c in r:
                if c is not None and id(c) not in shifted:
                    c.r0 += offset
                    shifted.add(id(c))
            rows.append(r)
    width = max(len(r) for r in rows)
    return [list(r) + [None] * (width - len(r)) for r in rows]


# ---------- 渲染 ----------

NOTE_LABELS = ("備註", "備考", "註：", "注意")


def detect_header_rows(rows):
    """自頂部起，凡列內有跨欄（colspan>1）之儲存格者視為表頭列，至多 4 列。"""
    n = 0
    for r in rows[: min(4, max(len(rows) - 1, 1))]:
        cells = {id(c): c for c in r if c}
        if any(c.cs > 1 or c.rs > 1 for c in cells.values()):
            n += 1
        else:
            break
    return max(n, 1)


def header_labels(rows, header_rows, label_skip=0):
    """各欄標籤＝表頭區內覆蓋該欄之相異儲存格文字（由上而下）串接。"""
    ncols = len(rows[0])
    labels = []
    for j in range(ncols):
        parts, seen = [], set()
        for i in range(min(header_rows, len(rows))):
            c = rows[i][j]
            if c is None or id(c) in seen:
                continue
            seen.add(id(c))
            if i < label_skip and c.cs > 1:
                continue  # 略過最上層跨欄群組標題
            if c.text and c.text not in parts:
                parts.append(c.text)
        labels.append(" ".join(parts))
    return labels


def is_note_row(row):
    first = next((c for c in row if c), None)
    if first is None:
        return False
    ncols = len(row)
    return (first.text.startswith(NOTE_LABELS) and
            sum(1 for c in {id(c): c for c in row if c}.values()) <= 2) or \
           (first.cs >= ncols and first.text.startswith(NOTE_LABELS))


def split_notes(rows, header_rows):
    body, notes = [], []
    for r in rows[header_rows:]:
        if is_note_row(r):
            cells = list({id(c): c for c in r if c}.values())
            label = cells[0].text if cells[0].text in ("備註", "備考") else ""
            text = "；".join(c.text for c in (cells[1:] if label else cells) if c.text)
            notes.append(f"> **{label or '備註'}**：{text}" if text else
                         f"> {cells[0].text}")
        else:
            body.append(r)
    return body, notes


def esc(s):
    return (s or "").replace("|", "／")


def render_grid(rows, header_rows, label_skip=0):
    labels = header_labels(rows, header_rows, label_skip)
    body, notes = split_notes(rows, header_rows)
    out = ["| " + " | ".join(esc(x) for x in labels) + " |",
           "|" + "---|" * len(labels)]
    for i, r in enumerate(body):
        vals = []
        for j, c in enumerate(r):
            if c is None:
                vals.append("")
            elif c.c0 < j:      # 橫向合併，僅左端輸出
                vals.append("〃")
            else:
                vals.append(esc(c.text))   # 縱向合併逐列重複（語意明確）
        out.append("| " + " | ".join(vals) + " |")
    if notes:
        out += [""] + notes
    return "\n".join(out)


def render_tree(rows, header_rows, label_skip=0):
    labels = header_labels(rows, header_rows, label_skip)
    body, notes = split_notes(rows, header_rows)
    blocks = []
    for i, r in enumerate(body):
        first = r[0]
        title = first.text if first else "（承上）"
        lines = [f"**{labels[0] or '項目'}：{title}**"]
        emitted = {id(first)}
        for j in range(1, len(r)):
            c = r[j]
            if c is None or id(c) in emitted:
                continue
            emitted.add(id(c))
            val = c.text or "—"
            if c.r0 < (first.r0 if first else 0) and len(val) > 12:
                val = "（同前列）"
            lines.append(f"- {labels[j]}：{val}")
        blocks.append("\n".join(lines))
    if notes:
        blocks.append("\n".join(notes))
    return "\n\n".join(blocks)


def detect_label_cols(rows, header_rows):
    ncols = len(rows[0])
    filled = [0] * ncols
    for r in rows[header_rows:]:
        for j, c in enumerate(r):
            if c is not None and c.c0 == j and c.text:
                filled[j] += 1
    for j in range(1, ncols):
        if filled[j] == 0:
            return j
    return min(2, ncols - 1)


def render_form(rows, header_rows, label_cols, label_skip=0):
    labels = header_labels(rows, header_rows, label_skip)
    ncols = len(rows[0])
    out = []
    field_names = []
    for x in labels[label_cols:]:
        if x and x not in field_names:
            field_names.append(x)
    if field_names:
        out.append("> 填寫欄位：" + "／".join(field_names) + "（表單填寫欄從略）")
    emitted = set()
    for i, r in enumerate(rows[header_rows:], start=header_rows):
        first = next((c for c in r if c), None)
        # 整列跨欄之章節列（如「外觀檢查」「性能檢查」）：以該儲存格所屬表格之欄數判定
        if first and first.cs >= first.w and id(first) not in emitted and first.text:
            emitted.add(id(first))
            if first.text.startswith(NOTE_LABELS) or len(first.text) > 30:
                out.append(f"- {first.text}")
            else:
                out.append(f"\n**{first.text}**")
            continue
        line_cells = []
        for j in range(min(label_cols, len(r))):
            c = r[j]
            if c is None or id(c) in emitted or not c.text:
                continue
            emitted.add(id(c))
            line_cells.append((c.c0, c.text))
        rest = []
        for j in range(label_cols, len(r)):
            c = r[j]
            if c is None or id(c) in emitted or not c.text:
                continue
            emitted.add(id(c))
            rest.append(c.text)
        for c0, text in line_cells:
            out.append("  " * c0 + f"- {text}")
        if rest:
            depth = (line_cells[-1][0] + 1) if line_cells else label_cols
            joined = "；".join(rest)
            if line_cells and len(joined) <= 40:
                out[-1] += f"（{joined}）"
            else:
                out.append("  " * depth + f"- {joined}")
    return "\n".join(out)


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", required=True, help="頁碼或範圍，如 278 或 271-272")
    ap.add_argument("--table", type=int, default=None)
    ap.add_argument("--mode", choices=["grid", "tree", "form"], default="grid")
    ap.add_argument("--header-rows", type=int, default=None)
    ap.add_argument("--label-skip", type=int, default=0)
    ap.add_argument("--label-cols", type=int, default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--raw", action="store_true")
    a = ap.parse_args()

    p0, p1 = (map(int, a.pages.split("-")) if "-" in a.pages
              else (int(a.pages), int(a.pages)))
    p0, p1 = int(p0), int(p1)

    pdf = pdfplumber.open(a.pdf)
    found = []
    for pno in range(p0, p1 + 1):
        page = pdf.pages[pno - 1]
        for ti, tb in enumerate(page.find_tables()):
            found.append((pno, ti, tb, page))
    if a.list:
        for pno, ti, tb, page in found:
            g = build_grid(tb, page)
            head = next((c.text for c in g[0] if c and c.text), "") if g else ""
            print(f"p{pno} 表{ti}: {len(g)} 列 x {len(g[0]) if g else 0} 欄  首格：{head[:30]}")
        return
    if a.table is not None:
        found = [found[a.table]]
    grids = [build_grid(tb, page) for _, _, tb, page in found]
    rows = stitch(grids)
    if not rows:
        sys.exit("指定頁面未偵測到線框表格")
    if a.raw:
        for r in rows:
            print([(c.text if c else None) for c in r])
        return
    hr = a.header_rows if a.header_rows is not None else detect_header_rows(rows)
    if a.mode == "grid":
        print(render_grid(rows, hr, a.label_skip))
    elif a.mode == "tree":
        print(render_tree(rows, hr, a.label_skip))
    else:
        lc = a.label_cols if a.label_cols is not None else detect_label_cols(rows, hr)
        print(render_form(rows, hr, lc, a.label_skip))


if __name__ == "__main__":
    main()
