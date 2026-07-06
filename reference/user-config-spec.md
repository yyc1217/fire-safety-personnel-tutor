# 使用者設定與進度檔共用規格（user-config-spec）

> 本文件為 exam-tutor、exam-trend-forecast、statute-memorizer、exam-archive 共用的**單一規格來源**。
> 各 SKILL.md 只引用本文件，不各自重複定義，避免規格漂移。

## 鐵則

1. **寫入邊界**：一切使用者資料只寫在 `data_dir` 之下；`${CLAUDE_PLUGIN_ROOT}`（plugin 目錄，含 `corpus/`、`statutes/`、`reference/`）一律**唯讀**。
2. **初次詢問並記住**：設定問過一次就記住，之後不再重複詢問；使用者可隨時以 `/設定` 重跑。
3. `weakness_tracking = "none"` 時完全不寫任何檔案，且不再重複詢問是否記錄。

## 目錄結構

```
~/.fire-safety-tutor/           ← 預設 data_dir（使用者可改）
├── config.json                 ← 使用者設定
├── progress.json               ← 作答與弱點紀錄（weakness_tracking = "auto" 才建立）
├── notes/                      ← 複習筆記庫（記憶重點、對照表、弱點筆記等，使用者選擇存檔時）
└── forecasts/                  ← 猜題產物（趨勢報告、猜題清單、懶人包、申論擬答）
```

## config.json

```json
{
  "level": "師",
  "weakness_tracking": "auto",
  "data_dir": "~/.fire-safety-tutor",
  "created": "2026-07-06",
  "updated": "2026-07-06"
}
```

| 欄位 | 值 | 影響 |
|------|----|------|
| `level` | `"師"`／`"士"` | 師：六科全申論（火災學、消防法規、警報、避難、水、化學系統）。士：四科申論＋測驗混合（火災學概要、法規概要、警報與避難概要、水與化學概要）。影響 exam-tutor 出題科目與題型比重、exam-trend-forecast 猜題科目範圍與申論/測驗考點配比。 |
| `weakness_tracking` | `"auto"`／`"notes"`／`"none"` | `auto`：作答後自動寫入 `progress.json`，弱點複習時自動讀取。`notes`：不寫 progress.json，每次練習結束產出一份錯題與弱點筆記，問使用者「存入 `notes/` 或看完即可」（記住偏好）。`none`：完全不記錄、不寫檔、不再詢問。 |
| `data_dir` | 路徑 | 所有使用者資料的根目錄；`~` 展開為使用者家目錄。 |

## progress.json（weakness_tracking = "auto"）

```json
{
  "attempts": [
    {"date": "2026-07-06", "level": "師", "subject": "化學系統", "q_id": "師/113/0806#3",
     "score": 60, "max": 100, "weak_topics": ["by_equipment:滅火器", "by_article:設置標準第31條"], "note": ""}
  ],
  "asked_ids": ["師/113/0806#3"],
  "weak_tally": {"by_equipment:滅火器": 2, "by_article:設置標準第31條": 1},
  "coverage": {"滅火器": {"done": ["設置標準14", "設置標準31"], "next": "設置標準223"}}
}
```

- `weak_tally` 與 `weak_topics` 的 key **對齊 `corpus/tags_index.json` 的維度**（`by_equipment:<設備>`、`by_article:<法規條號>`、`by_system:<系統>`），弱點複習時可直接用 jq 對 `tags_index.json` 取單鍵反查題目。
- `coverage` 記錄各設備依 `reference/設備條文索引.md` 的條文覆蓋進度（對應使用者原始試算表的「進度」欄），供「接下來還有哪些條文沒考」與主動提議下一個設備使用。
- `q_id` 格式沿用 corpus 題目參照：`等別/年/科目代號#題號`。

## 初次詢問流程

任一 skill 需要等別或記錄模式時：

1. 先讀 `~/.fire-safety-tutor/config.json`（或使用者先前告知的 data_dir）。
2. **存在** → 直接使用，不再詢問。
3. **不存在** → 一次問完兩題再開始正題：
   - (a) 應考等別：消防設備師（六科全申論）或消防設備士（四科申論＋測驗混合）？
   - (b) 弱點記錄模式：自動記錄到本機進度檔／每次產出複習筆記由你自行保存／不記錄？（說明三者差異）
   - 徵得同意後建立 `data_dir` 目錄與 `config.json`。
4. 使用者要求改設定、或執行 `/設定` → 重跑本流程並更新 `updated` 日期。

## 檔案命名慣例（各 skill 輸出）

| 產物 | 路徑 | 命名 |
|------|------|------|
| 趨勢報告 | `forecasts/` | `趨勢報告_<等別><民國年>_<YYYY-MM-DD>.md` |
| 猜題清單 | `forecasts/` | `猜題清單_<等別><民國年>.md`（同年同等別續用同一檔，支援勾銷接續） |
| 考前必背懶人包 | `forecasts/` | `考前必背懶人包_<等別><民國年>.md` |
| 申論猜題擬答 | `forecasts/` | `申論猜題擬答_<等別><民國年>_<科目>.md` |
| 複習／弱點筆記 | `notes/` | `<YYYY-MM-DD>_<主題>.md`（如 `2026-07-06_水系統弱點筆記.md`） |

原則：**等別＋民國年**入檔名者為同年續用之工作檔（可勾銷、可增補）；**日期**入檔名者為快照型產物。
