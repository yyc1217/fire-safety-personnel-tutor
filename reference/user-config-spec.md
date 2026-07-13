# 使用者設定與進度檔共用規格（user-config-spec）

> 本文件為 exam-tutor、exam-trend-forecast、statute-memorizer、exam-archive 共用的**單一規格來源**。
> 各 SKILL.md 只引用本文件，不各自重複定義，避免規格漂移。

## 鐵則

1. **寫入邊界**：一切使用者資料只寫在 `data_dir` 之下；`${CLAUDE_PLUGIN_ROOT}`（plugin 目錄，含 `corpus/`、`statutes/`、`reference/`）一律**唯讀**。
2. **初次詢問並記住**：設定問過一次就記住，之後不再重複詢問；使用者可隨時以 `/備考設定` 重跑。
3. `weakness_tracking = "none"` 時完全不寫任何檔案，且不再重複詢問是否記錄。

## 目錄結構

```
~/.fire-safety-tutor/           ← 預設 data_dir（使用者可改）
├── config.json                 ← 使用者設定
├── progress.json               ← 作答與弱點紀錄（weakness_tracking = "auto" 才建立）
├── notes/                      ← 複習筆記庫（記憶重點、對照表、弱點筆記等，使用者選擇存檔時）
├── plans/                      ← 讀書計畫（study-planner）
└── forecasts/                  ← 猜題產物（趨勢報告、懶人包、申論擬答）
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
| `level` | `"師"`／`"士"` | 師：6 科（火災學、消防法規、警報、避難、水、化學系統）；其中火災學與四系統為**全申論**、**消防法規為申論 2 題＋測驗 40 題混合**。士：4 科（火災學概要、法規概要、警報與避難概要、水與化學概要），**皆為申論 2 題＋測驗 40 題混合**。影響 exam-tutor 出題科目與題型比重、exam-trend-forecast 猜題科目範圍與測驗高頻數字配置。（勿誤植「師六科全申論」。） |
| `weakness_tracking` | `"auto"`／`"notes"`／`"none"` | `auto`：作答後自動寫入 `progress.json`，弱點複習時自動讀取。`notes`：不寫 progress.json，每次練習結束產出一份錯題與弱點筆記，問使用者「存入 `notes/` 或看完即可」（記住偏好）。`none`：完全不記錄、不寫檔、不再詢問。 |
| `data_dir` | 路徑 | 所有使用者資料的根目錄；`~` 展開為使用者家目錄。 |
| `exam_date` | `YYYY-MM-DD` 或民國格式 | 目標考試日期。**初次使用 study-planner 時必先確認**：無此值時主動推算預設——消防設備人員考試**原則上於每年六月的第一個週末舉行（週六、週日兩天）**，取「下一個六月的第一個週六」供使用者確認或改為考選部公告日期；確認後記入，不再重複詢問。 |
| `weekly_hours` | 選填，數字 | 每週可用讀書時數。**不主動詢問**——進度以「各設備單元規定是否逐步掌握」衡量，不以時數為主；使用者主動提供時記入，僅供排程參考。 |
| `progress_reminder` | 選填，`"auto"`（預設）／`"off"` | 讀書進度有趕不上跡象時是否主動提醒（study-planner）：`auto` 主動提醒並提議重排；`off` 僅在使用者詢問進度時說明。使用者表明偏好時記入。 |

## progress.json（weakness_tracking = "auto"）

```json
{
  "attempts": [
    {"date": "2026-07-06", "level": "師", "subject": "化學系統", "q_id": "師/113/0806#3",
     "score": 15, "max": 25, "weak_topics": ["by_equipment:滅火器", "by_article:設置標準第31條"], "note": ""}
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
   - (a) 應考等別：消防設備師（6 科；5 科全申論＋消防法規混合）或消防設備士（4 科皆申論＋測驗混合）？
   - (b) 弱點記錄模式：自動記錄到本機進度檔／每次產出複習筆記由你自行保存／不記錄？（說明三者差異）
   - 徵得同意後建立 `data_dir` 目錄與 `config.json`。
4. 使用者要求改設定、或執行 `/備考設定` → 重跑本流程並更新 `updated` 日期。

## 檔案命名慣例（各 skill 輸出）

| 產物 | 路徑 | 命名 |
|------|------|------|
| 趨勢報告（猜題範圍） | `forecasts/` | `趨勢報告_<等別><民國年>_<YYYY-MM-DD>.md`（exam-trend-forecast） |
| 考前必背懶人包 | `forecasts/` | `考前必背懶人包_<等別><民國年>.md`（statute-memorizer） |
| 申論猜題擬答 | `forecasts/` | `申論猜題擬答_<等別><民國年>_<科目>.md`（exam-tutor） |
| 複習／弱點筆記 | `notes/` | `<YYYY-MM-DD>_<主題>.md`（如 `2026-07-06_水系統弱點筆記.md`） |
| 讀書計畫 | `plans/` | `讀書計畫_<等別><民國年>.md`（同年同等別續用同一檔，支援勾銷與重排） |

原則：**等別＋民國年**入檔名者為同年續用之工作檔（可勾銷、可增補）；**日期**入檔名者為快照型產物。

**`<民國年>` 一律＝目標考試年度（下一次考試年）**，各 skill 計算方式須一致，避免同一批產物落在不同年份：有 `exam_date` 時取其民國年；無 `exam_date` 時比照 study-planner 之推算——取「下一個六月第一個週六」所在年（今日已過當年六月考期則為次年）。**不得以「今年」（當前系統年）充當考試年**。
