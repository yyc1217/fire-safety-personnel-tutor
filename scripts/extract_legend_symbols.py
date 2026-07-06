#!/usr/bin/env python3
"""將「附件三 消防圖說圖示範例」PDF 轉為可出題的結構化圖例資料。

輸入：
  statutes/附件/消防機關辦理建築物消防安全設備審查及查驗作業基準/附件三：消防圖說圖示範例.PDF
  scripts/legend_names.json（人工逐字轉寫之類別／名稱／備註）

輸出（皆位於上述附件資料夾內）：
  附件三_圖例/<類別序2位>_<項序2位>_<名稱>.png   逐格裁切之圖例符號
  附件三：消防圖說圖示範例.md                     圖例↔名稱對照表（出題主入口）
  附件三_圖例_index.json                          機器可讀索引（隨機抽題用）

作法：以 pdftoppm 300dpi 轉頁圖，偵測表格橫線切列、以全表眾數定欄界，
裁切「圖例」欄存圖；列數與 legend_names.json 逐類核對，不符即中止。

相依：poppler-utils（pdftoppm）、pillow、numpy。
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTACH_DIR = os.path.join(
    REPO, "statutes", "附件", "消防機關辦理建築物消防安全設備審查及查驗作業基準")
PDF = os.path.join(ATTACH_DIR, "附件三：消防圖說圖示範例.PDF")
NAMES_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legend_names.json")
OUT_IMG_DIR = os.path.join(ATTACH_DIR, "附件三_圖例")
OUT_MD = os.path.join(ATTACH_DIR, "附件三：消防圖說圖示範例.md")
OUT_INDEX = os.path.join(ATTACH_DIR, "附件三_圖例_index.json")

DARK = 128          # 灰階二值化門檻
MIN_INK = 25        # 圖例格少於此暗像素數視為空白列
RED_MIN = 60        # 列帶紅色像素數超過此值視為紅字列


def find_tables(dark):
    """回傳頁面上各表格：(x0, x1, rows)；rows 為 (y0, y1, 欄分隔線x清單)。

    橫線＝整行過半為暗像素；表格切分＝相鄰橫線間左框線是否連續。
    欄分隔線以「全表各列候選位置眾數」決定，避免符號內部直線誤判。
    標題列（跨全寬、無內部分隔線）之 seps 為空清單。
    """
    h, w = dark.shape
    row_counts = dark.sum(axis=1)
    line_rows = np.where(row_counts > w * 0.55)[0]
    hlines = []
    for y in line_rows:
        if hlines and y <= hlines[-1][1] + 3:
            hlines[-1][1] = y
        else:
            hlines.append([y, y])
    if not hlines:
        return []
    ys, ye = hlines[0]
    cols = np.where(dark[ys:ye + 1].any(axis=0))[0]
    x0, x1 = int(cols.min()), int(cols.max())

    tables, cur = [], [hlines[0]]
    for prev, nxt in zip(hlines, hlines[1:]):
        seg = dark[prev[1] + 1:nxt[0], max(0, x0 - 2):x0 + 8]
        frac = seg.any(axis=1).mean() if seg.size else 0
        if frac > 0.9:
            cur.append(nxt)
        else:
            tables.append(cur)
            cur = [nxt]
    tables.append(cur)

    out = []
    for t in tables:
        if len(t) < 2:
            continue
        rows = []
        for top, bot in zip(t, t[1:]):
            y0, y1 = top[1] + 1, bot[0] - 1
            band = dark[y0:y1 + 1]
            col_frac = band.mean(axis=0)
            vcols = np.where(col_frac > 0.85)[0]
            inner = [x for x in vcols if x0 + 15 < x < x1 - 15]
            seps = []
            for x in inner:
                if seps and x <= seps[-1][1] + 3:
                    seps[-1][1] = x
                else:
                    seps.append([x, x])
            rows.append((int(y0), int(y1), [int((a + b) / 2) for a, b in seps]))
        all_seps = sorted(x for _, _, s in rows for x in s)
        clusters = []
        for x in all_seps:
            if clusters and x <= clusters[-1][-1] + 6:
                clusters[-1].append(x)
            else:
                clusters.append([x])
        table_seps = [int(np.median(c)) for c in clusters if len(c) > 0.55 * len(rows)]
        fixed = [(y0, y1, [] if not s else table_seps) for y0, y1, s in rows]
        out.append((x0, x1, fixed))
    return out


def extract_rows():
    """走訪全 PDF，回傳 [(cat_no, item_no, legend_rgb_or_None, is_red)]（依閱讀順序）。"""
    tmp = tempfile.mkdtemp(prefix="fig3_")
    subprocess.run(["pdftoppm", "-r", "300", "-png", PDF, os.path.join(tmp, "p")],
                   check=True)
    pages = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))

    results = []
    cat = idx = 0
    expect_header = False
    for pg in pages:
        im = Image.open(os.path.join(tmp, pg))
        rgb = np.asarray(im.convert("RGB"))
        gray = np.asarray(im.convert("L"))
        dark = gray < DARK
        for x0, x1, rows in find_tables(dark):
            for y0, y1, seps in rows:
                if not seps:            # 類別標題列
                    cat += 1
                    idx = 0
                    expect_header = True
                    continue
                if expect_header:       # 表頭列（圖例｜名稱｜備註）
                    expect_header = False
                    continue
                sep1 = seps[0]
                legend = gray[y0 + 4:y1 - 3, x0 + 6:sep1 - 4]
                ys_, xs_ = np.where(legend < 200)
                if len(ys_) == 0 or (legend < 200).sum() < MIN_INK:
                    idx += 1
                    results.append((cat, idx, None, False))
                    continue
                cy0 = max(0, int(ys_.min()) - 8)
                cy1 = min(legend.shape[0], int(ys_.max()) + 8)
                cx0 = max(0, int(xs_.min()) - 8)
                cx1 = min(legend.shape[1], int(xs_.max()) + 8)
                crop = rgb[y0 + 4 + cy0:y0 + 4 + cy1, x0 + 6 + cx0:x0 + 6 + cx1]
                # 紅字判定僅看「圖例＋名稱」欄；備註欄紅字屬類別備註，非該列本身
                band_x1 = seps[1] if len(seps) > 1 else x1
                band = rgb[y0:y1 + 1, x0:band_x1].astype(int)
                red = ((band[:, :, 0] > 150) & (band[:, :, 1] < 110)
                       & (band[:, :, 2] < 110)).sum() > RED_MIN
                idx += 1
                results.append((cat, idx, crop, bool(red)))
    return results


def main():
    with open(NAMES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    cats = data["categories"]

    rows = extract_rows()
    # 依類別聚合，去除空白列（原檔即為空的預留列，皆在表尾）
    by_cat = {}
    for cat, idx, crop, red in rows:
        by_cat.setdefault(cat, []).append((idx, crop, red))
    filled = {c: [(i, cr, rd) for i, cr, rd in v if cr is not None]
              for c, v in by_cat.items()}

    if len(filled) != len(cats):
        sys.exit(f"類別數不符：偵測 {len(filled)}，轉寫 {len(cats)}")
    for ci, cat_def in enumerate(cats, 1):
        if len(filled[ci]) != len(cat_def["items"]):
            sys.exit(f"第 {ci} 類「{cat_def['name']}」列數不符："
                     f"偵測 {len(filled[ci])}，轉寫 {len(cat_def['items'])}")

    os.makedirs(OUT_IMG_DIR, exist_ok=True)
    index = {"title": data["title"], "source": data["source"],
             "source_file": os.path.basename(PDF),
             "transcription_note": data["transcription_note"],
             "categories": []}
    md = []
    md.append("# 附件三 消防圖說圖示範例（圖例對照表）\n")
    md.append(f"> 來源：{data['source']}（原始檔：[附件三：消防圖說圖示範例.PDF](附件三：消防圖說圖示範例.PDF)）\n>\n"
              "> 📌 **免責聲明**：本表之圖例為原 PDF 300dpi 逐格裁切影像，名稱由影像辨識"
              "轉寫；原檔錯漏字經使用者確認後已更正，並於備註保留修改痕跡（原檔誤作「…」，"
              "已更正）。一切以主管機關（內政部消防署）公告之現行版本為準。\n")
    md.append("\n## 用途與使用方式（給出題 agent）\n\n"
              "消防圖說圖例雖未在命題大綱明列，但屬考題來源（識圖題）。出題方式建議：\n\n"
              "1. **看圖答名**：呈現圖例圖檔，問設備名稱（可搭配所屬設備類別提示）。\n"
              "2. **依名選圖**：給設備名稱，從同類別相似圖例中選正確者（同類別內符號相似度高，適合做選項）。\n"
              "3. **加註規則**：數個類別備註欄訂有加註規則（滅火器藥劑、揚聲器等級／W 數、標示燈等級、住警器 R 等），本身即為考點。\n\n"
              "機器可讀索引：[`附件三_圖例_index.json`](附件三_圖例_index.json)，"
              "可用 `jq` 隨機抽題，例如：`jq '.categories[].items[]' 附件三_圖例_index.json`。\n"
              "同一符號（底閥、制水閥、逆止閥、防震軟管等）依原檔重複列於多個系統，出題時脈絡不同，未去重。\n")

    total = 0
    for ci, cat_def in enumerate(cats, 1):
        items_out = []
        md.append(f"\n## {ci}. {cat_def['name']}\n")
        md.append("| 圖例 | 名稱 | 備註 |")
        md.append("|------|------|------|")
        for (idx, crop, red), item in zip(filled[ci], cat_def["items"]):
            name = item["name"]
            iid = f"{ci:02d}_{idx:02d}"
            fname = f"{iid}_{name}.png"
            Image.fromarray(crop).save(os.path.join(OUT_IMG_DIR, fname))
            remarks = []
            if item.get("remark"):
                remarks.append(item["remark"])
            if red:
                remarks.append("🔴 原檔紅字（較新修正處）")
            rel = f"附件三_圖例/{fname}"
            md.append(f"| ![{name}]({rel}) | {name} | {'；'.join(remarks)} |")
            entry = {"id": iid, "name": name, "image": rel, "red": red}
            if item.get("remark"):
                entry["remark"] = item["remark"]
            items_out.append(entry)
            total += 1
        if cat_def.get("note"):
            md.append(f"\n> **加註規則（原檔備註）**：{cat_def['note']}")
        cat_entry = {"id": ci, "name": cat_def["name"], "items": items_out}
        if cat_def.get("note"):
            cat_entry["note"] = cat_def["note"]
        index["categories"].append(cat_entry)

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    with open(OUT_INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print(f"完成：{total} 個圖例 → {OUT_IMG_DIR}")
    print(f"對照表：{OUT_MD}")
    print(f"索引：{OUT_INDEX}")


if __name__ == "__main__":
    main()
