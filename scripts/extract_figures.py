#!/usr/bin/env python3
"""擷取原卷 PDF 中的圖形題圖片，輸出至引用之 md 檔同資料夾（corpus/md/<類>/<年>/）。

用途：issue #3「① 圖形題」——將題幹／選項圖形自原卷 PDF 裁切為 PNG，
供 corpus/md/ 內嵌顯示（取代「請對照原 PDF 作答」占位文字）。

作法（不需 OCR 模型，於無 GPU 環境可執行）：
- raster 模式：選項圖為 PDF 內嵌點陣圖（xobject），以 get_image_rects 取得
  各圖在頁面上的位置，依 x 座標由左至右對應選項 (A)~(D)，以含 2pt 邊距之
  區域高解析度渲染輸出（渲染而非直接抽 xobject，可正確處理遮罩與色彩空間）。
- clip 模式：題幹圖為向量繪圖，以人工核定之裁切框（PDF 點座標）渲染輸出。
  裁切框由逐頁目視原卷後定案，成品經逐張人工核對。

執行：python3 scripts/extract_figures.py   （於 repo 根目錄）
需求：pip install pymupdf
"""
import os
import sys

import fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ROOT = os.path.join(ROOT, "corpus", "md")  # 圖片與引用之 md 同資料夾

# dpi：選項小圖原生解析度低（46~107px），300dpi 渲染已足；大型向量圖 220dpi。
MANIFEST = [
    # 士/100/0910 Q7（密閉式撒水頭圖例）、Q8（綜合消防栓箱圖例）：第 2 頁 8 張點陣圖
    {"mode": "raster", "pdf": "corpus/pdf/士/100/0910_水與化學系統消防安全設備概要.pdf",
     "page": 2, "yband": (245, 285), "out": "士/100/0910_Q7_{}.png", "dpi": 300},
    {"mode": "raster", "pdf": "corpus/pdf/士/100/0910_水與化學系統消防安全設備概要.pdf",
     "page": 2, "yband": (286, 330), "out": "士/100/0910_Q8_{}.png", "dpi": 300},
    # 士/104/0707 Q34（化學品危害圖示）：第 4 頁 4 張點陣圖
    {"mode": "raster", "pdf": "corpus/pdf/士/104/0707_火災學概要.pdf",
     "page": 4, "yband": (400, 440), "out": "士/104/0707_Q34_{}.png", "dpi": 300},
    # 士/111/0809 Q35（揚聲器音域圖）：第 6 頁 4 張點陣圖
    {"mode": "raster", "pdf": "corpus/pdf/士/111/0809_警報與避難系統消防安全設備概要.pdf",
     "page": 6, "yband": (240, 325), "out": "士/111/0809_Q35_{}.png", "dpi": 300},
    # 師/114/0801 甲2：單一開口室內火災中性帶示意圖（第 1 頁，向量圖）
    {"mode": "clip", "pdf": "corpus/pdf/師/114/0801_火災學.pdf",
     "page": 1, "rect": (155, 549, 435, 675), "out": "師/114/0801_甲2.png", "dpi": 220},
    # 師/115/0801 甲2：輻射熱通量示意圖（第 1 頁，向量圖）
    {"mode": "clip", "pdf": "corpus/pdf/師/115/0801_火災學.pdf",
     "page": 1, "rect": (145, 445, 445, 650), "out": "師/115/0801_甲2.png", "dpi": 220},
    # 師/115/0801 甲4：三串接空間氣流示意圖（第 2 頁，向量圖）
    {"mode": "clip", "pdf": "corpus/pdf/師/115/0801_火災學.pdf",
     "page": 2, "rect": (165, 240, 425, 435), "out": "師/115/0801_甲4.png", "dpi": 220},
]

OPTION_LABELS = ["A", "B", "C", "D"]
PAD = 0  # raster 模式裁切邊距（pt）；>0 會沾到選項括號與鄰行文字


def save_clip(page, rect, out_rel, dpi):
    pix = page.get_pixmap(clip=fitz.Rect(rect), dpi=dpi)
    out = os.path.join(OUT_ROOT, out_rel)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pix.save(out)
    print(f"  {out_rel}  ({pix.width}x{pix.height}px)")


def run(entry):
    doc = fitz.open(os.path.join(ROOT, entry["pdf"]))
    page = doc[entry["page"] - 1]
    if entry["mode"] == "clip":
        save_clip(page, entry["rect"], entry["out"], entry["dpi"])
        return
    # raster：收集 y 帶內的內嵌圖位置，由左至右對應 (A)~(D)
    rects = []
    for img in page.get_images(full=True):
        for r in page.get_image_rects(img[0]):
            y0, y1 = entry["yband"]
            if y0 <= r.y0 <= y1:
                rects.append(r)
    rects.sort(key=lambda r: r.x0)
    if len(rects) != len(OPTION_LABELS):
        sys.exit(f"預期 {len(OPTION_LABELS)} 張選項圖，實得 {len(rects)}：{entry}")
    for label, r in zip(OPTION_LABELS, rects):
        clip = (r.x0 - PAD, r.y0 - PAD, r.x1 + PAD, r.y1 + PAD)
        save_clip(page, clip, entry["out"].format(label), entry["dpi"])


def main():
    print(f"輸出目錄：{OUT_ROOT}")
    for entry in MANIFEST:
        print(f"{entry['pdf']} p{entry['page']}")
        run(entry)


if __name__ == "__main__":
    main()
