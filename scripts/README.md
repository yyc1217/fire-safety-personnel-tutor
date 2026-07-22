# scripts/ 工具腳本一覽

維護題庫索引與法規轉檔的 Python 腳本。皆為**維護者本機工具**，skill 執行時不呼叫（skill 只讀取其產物）。

## 題庫索引（標籤系統）

| 腳本 | 用途 |
|------|------|
| `rebuild_index.py` | 從各題 inline `🏷️` 標籤**反向建立** `corpus/tags_index.json`。不重新判讀題目——inline 標籤（人工／語意校正結果）為唯一真相來源；校正分類請直接編輯 md 的 `🏷️` 行後執行本腳本。 |
| `analyze_corpus.py` | 由 `tags_index.json` 計算命題頻率與趨勢，產出 `corpus/tags_summary.json`（精簡計數索引，skill 直接載入）與 `corpus/命題頻率分析.md`（人可讀報告）。 |
| `analyze_cycles.py` | 由 `tags_index.json` 計算各考點**出題週期型態**（常年型／新興熱點／週期到期／冷卻中／一次性／偶發＋未考缺口），依等別分拆，產出 `corpus/tags_cycles.json` 與 `corpus/命題週期分析.md`，供 exam-trend-forecast 猜題使用。 |
| `build_tags.py` | ⚠️ **已停用（DEPRECATED，2026-06）**：關鍵字自動判讀準確度不足，其結果會覆蓋語意標籤。**保留原因**：其 EQUIP／LAWS／TOPICS 詞彙表仍供 `rebuild_index.py` 匯入；執行時直接報錯擋下。 |

標準流程：編輯題目 `🏷️` 行 → `python3 scripts/rebuild_index.py` → `python3 scripts/analyze_corpus.py` → `python3 scripts/analyze_cycles.py`。

## 命題分析（探索性，不回寫標籤）

| 腳本 | 用途 |
|------|------|
| `analyze_repeat_granularity.py` | 驗證命題「前一年考過的考點今年不會再考」之可信度：以**四層顆粒度**（設備／組件／子考點／子子考點）計算重考率，並以**置換檢定**（隨機基準）判斷是否真有「迴避去年考點」效應。詞庫見 `repeat_lexicon.json`，產出 `corpus/命題重考率分析.md` 與 `corpus/repeat_granularity.json`。⚠️ 子考點以下採**關鍵字啟發式**分桶（準確度有限，同 `build_tags.py` 之教訓），**絕不回寫** `tags_index.json`／inline `🏷️` 語意標籤；方法學與警語見 `docs/設計_重考率與顆粒度分析.md`。 |

## 題庫品質校核（issue #3）

| 腳本 | 用途 |
|------|------|
| `check_option_order.py` | 測驗題選項順序全面比對：取原卷 PDF 內部文字流與 md 逐題比對，防兩欄版面重排造成的選項錯置。 |
| `extract_figures.py` | 自原卷 PDF 裁切圖形題圖片為 PNG，輸出至引用之 md 同資料夾（`corpus/md/<類>/<年>/`），供 md 內嵌顯示。 |
| `extract_legend_symbols.py` | 將「附件三 消防圖說圖示範例」PDF 轉為可出題的結構化圖例資料（284 圖例＋機器索引）。搭配 `legend_names.json`（人工逐字轉寫之類別／名稱／備註資料檔）。 |

## 法規轉檔（statutes 入庫）

| 腳本 | 用途 |
|------|------|
| `rtf2md_statute.py` | 全國法規資料庫匯出之 RTF（Big5）→ 章條分明的 Markdown。 |
| `html2md_statute.py` | 消防署「消防法令查詢系統」HTML（基準／要點類，`<pre>` 區塊）→ Markdown。 |
| `pdf2md_statute.py` | 政府公報型 PDF（檢修基準／認可基準，`pdftotext -layout`）→ Markdown。 |
| `check_statute_versions.py` | 比對 `statutes/` 各檔檔首版本日期與 `docs/法規版本追蹤.md` 核對紀錄表，列出 🔴 過期／⚪ 未核對／✅ 現行；有過期時以非零值結束（`--stale-only` 只列問題檔）。 |

轉檔後均需人工核對（CLAUDE.md：OCR 免責與查證、公式一律 LaTeX、附表處理原則）。

## 附註

- `corpus/pdf/`（37 MB）與 `statutes/原始檔案/`（48 MB）為官方原卷／附表原始檔，屬**資料資產**，刻意入庫供 AI 與使用者查對，非垃圾大檔。
