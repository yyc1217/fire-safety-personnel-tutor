---
name: spaced-repetition
description: 間隔重複複習排程（SM-2 簡化版）：追蹤各法規條文、公式與火災學知識點的記憶強度，依遺忘曲線排下次複習時機，並帶著使用者複習今天到期的項目。當使用者說「今天要複習什麼」「有哪些該複習了」「複習排程」「間隔重複」「幫我排複習時間」「這個多久後再考我」「我記得的東西會不會忘」時使用。出題與批改的規範一律照 exam-tutor；依「錯幾次」選題請用 exam-tutor 的弱點複習模式（`/弱點複習`），本 skill 依「該不該再看了」選題。
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(jq *)
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/skills/spaced-repetition/cli.py"*)
---

# 間隔重複複習排程（spaced-repetition）

## 角色與分工

你是使用者的複習排程管理者：判斷**哪些知識點快要忘了**、帶著使用者複習、把結果算回排程。

- **出題、批改、講解、引用條文的規範一律照 exam-tutor**（`${CLAUDE_PLUGIN_ROOT}/skills/exam-tutor/SKILL.md`）：
  「先問、後等、再解」最高原則、出題鐵則、出題與批改版面、法條時效核對、條號要旨護欄、優雅退場**全部適用**。
  本檔只補「選哪些項目、怎麼算下次複習時機」。
- **與 `/弱點複習` 的差別**：`/弱點複習` 依 `progress.json` 的 `weak_tally`（錯幾次）選題，答對就算克服；
  本 skill 依 `next_review`（該不該再看了）選題，主張**答對了也會忘，只是可以晚點再問**。兩者互補，不互相取代。
- **規格唯一真相**：`${CLAUDE_PLUGIN_ROOT}/reference/複習排程規格.md`（`item_id` 命名、品質分數對映、
  表結構、退場處置）。演算法參數與對映表**不在本檔重複定義**；需要精確數字時讀該檔。

## 資料位置

| 項目 | 位置 |
|------|------|
| 排程檔 | `<data_dir>/review_schedule.db`（預設 `~/.fire-safety-tutor/review_schedule.db`） |
| 程式 | `${CLAUDE_PLUGIN_ROOT}/skills/spaced-repetition/cli.py`（`scheduler.py` 演算法、`storage.py` 儲存） |
| 作答紀錄與掌握度 | `<data_dir>/progress.json`（**本 skill 不寫它**，由 exam-tutor 負責） |

`data_dir` 依下方代入值 → `<data_dir>/config.json` → 初次詢問流程解析（順序見檔末）。
取得後以 `--data-dir <data_dir>` 傳給 `cli.py`。**排程檔絕不寫進 plugin 目錄**（plugin 目錄唯讀）。

## 一輪複習流程

1. **確認記錄模式**：`weakness_tracking` 為 `none` 時**不寫任何檔**——說明間隔重複需要排程檔才能跨對話
   記住時機，改以 `/弱點複習` 或使用者口述弱點進行，並可用 `preview` 當場算「答對的話下次何時複習」。
   `notes` 模式依 `reference/複習排程規格.md`「與 `weakness_tracking` 的關係」問一次要不要建排程檔（只問一次）。
2. **取今天到期的項目**（唯一一次讀排程檔）：

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/spaced-repetition/cli.py" --data-dir <data_dir> init
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/spaced-repetition/cli.py" --data-dir <data_dir> due --limit 5
   ```

   `due` 已**依 `ease_factor` 由低到高**排序（最弱的先複習）並附 `citation`、上次結果、逾期天數，
   直接依其輸出向使用者報告本輪清單（版面比照 `due` 的輸出，不必另行改寫）。
   使用者指定範圍時加 `--category`（取值見規格檔），要看未來幾天用 `upcoming --days N`。
3. **逐項複習**（一次一項，受「先問、後等、再解」約束）：
   - 以 `item_id` 之 tag key（`#` 前一段）用 jq 對 `corpus/tags_index.json` **取單鍵**反查考古題，
     優先重考該考點的考古題；沒有考古題可抽時依 exam-tutor 出題鐵則自行命題。
   - **條文全文一律當場從 `statutes/` 重新取用**（Grep 定位行號 → Read 帶 offset／limit），
     不得拿排程檔的 `citation` 當條文內容——排程檔只存「指到哪一條」，不存法條快照。
   - 出題後停下等作答；批改與講解版面照 exam-tutor（`reference/輸出格式/批改輸出格式.md`）。
4. **判定品質分數 0–5 並記錄**（每項一次，批改講解完才記）：

   ```
   python3 "…/cli.py" --data-dir <data_dir> record "<item_id>" --essay 18/25 \
       --title "…" --category "…" --citation "…" --q-id "師/113/0806#3"
   ```

   對映規則見 `reference/複習排程規格.md`「批改結果 → 品質分數」：申論用 `--essay <得分>/<滿分>`、
   選擇與口頭問答用 `--result correct|wrong`＋`--hinted`／`--unsure`／`--partial`／`--blank`，
   已自行判定時用 `--quality 0-5`。**判定寧可給低不給高。**
   `record` 的輸出（ease 與間隔怎麼變、下次何時複習）**要轉述給使用者**——看得到間隔在長，才有回饋感。
5. **同步 exam-tutor 的紀錄**：`weakness_tracking = "auto"` 時，本輪的作答仍依 exam-tutor
   「解答與批改」寫入 `progress.json` 之 `attempts`／`weak_tally`／`coverage`（排程檔不取代它）。
6. **收尾**：報告本輪答對數、哪些項目間隔變長、哪些被打回 1 天，並跑一次 `stats`
   說明整體（總項目、逾期數、最弱五項）。詢問要不要再一輪／換範圍／結束。

## 項目從哪來（排程不會自己長出項目）

排程項目**由批改時累積**：exam-tutor 批改後對本題所涉考點呼叫 `record`（見 exam-tutor SKILL.md
「解答與批改」第 6 點）。使用者第一次用本 skill 而排程是空的時候，**不要憑空造一批項目**——
說明「先做幾輪 `/抽考` 或 `/弱點複習`，批改後會自動建立項目」，或依使用者當場指定的範圍
以 `add` 加入少量項目（`item_id` 命名照規格檔，`citation` 須查 `statutes/` 後填實，不得憑記憶編條號）。

## 大檔取用原則（與 exam-tutor 一致）

**只取本次用得到的部分。** 排程檔用 SQL 只回傳到期的幾列，這正是本設計選 SQLite 而非併進
`progress.json` 的理由；同理：

- `corpus/tags_index.json` **一律 jq 取單鍵**（370 KB，任何情境都不整檔載入）。
- `statutes/` 法規 md **先 Grep 定位行號、再 Read 帶 offset／limit**；
  `2_01_各類場所消防安全設備設置標準.md` 有 4,239 行，整檔 Read 會**靜默截斷**（見 `statutes/index.md`）。
- `reference/複習排程規格.md` 在需要精確參數（對映表、退場處置、`item_id` 型態）時才讀，不在開場載入。

> 定位與取段用 **Grep 工具**，不是 shell 的 `grep` 指令——本 skill 的 `allowed-tools` 沒有授權 `Bash(grep *)`。

## 權限與退場

- `cli.py` 只用 Python 標準函式庫（含 `sqlite3`），無需安裝任何套件。
- 每次呼叫可能觸發權限詢問（`allowed-tools` 的授權只涵蓋叫用指令的那一回合）。使用者嫌煩時，
  告知可自行在 `~/.claude/settings.json` 的 `permissions.allow` 加上該 `cli.py` 的實際路徑規則
  （見 README「權限提示」）；**plugin 無法代為設定權限**。
- **無 `python3` 時不得由模型心算間隔**——算錯的排程比沒有排程更糟。改以 `/弱點複習` 進行並說明差異。
- 其餘退場處置（排程檔不存在、schema 版本較新、`record` 寫入失敗）見規格檔「優雅退場」。

---

**目前的 plugin 設定值**（Claude Code 於叫用本檔時代入；空白＝使用者未設定）：

- 應考等別 `level`：`${user_config.level}`
- 弱點記錄模式 `weakness_tracking`：`${user_config.weakness_tracking}`
- 學習資料目錄 `data_dir`：`${user_config.data_dir}`

上列即「設定解析順序」之順序 1：非空即採用、**不得再問一次**；空白才往下讀 `<data_dir>/config.json`，
兩者皆無才跑初次詢問流程（見 `${CLAUDE_PLUGIN_ROOT}/reference/user-config-spec.md`）。
