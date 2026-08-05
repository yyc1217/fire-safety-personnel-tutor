---
name: fs-quiz
description: 【抽考】快速抽考一輪 3~5 題，適合零碎時間複習（可指定系統/設備/科目、題型與題數）
argument-hint: "[範圍] [題型 測驗/申論] [題數 預設5上限20]，皆可省略"
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(jq *)
  - Bash(date *)
---
使用 exam-tutor skill 進入「快速抽考模式」——**先讀 `${CLAUDE_PLUGIN_ROOT}/skills/exam-tutor/modes/快速抽考.md`**（該檔為本模式規範唯一真相），再依其執行：先依「設定解析順序」載入使用者設定（下列 plugin 設定 → `<data_dir>/config.json` → 初次詢問），一輪出 3~5 題、快節奏一題一答一講。**開始出題前先跑「續作偵測」**：`weakness_tracking = "auto"` 時讀 `<data_dir>/progress.json` 之 `pending`，上次有沒答完的題就先問要接續或重開。

**參數（範圍／題型／題數）之解析、題數上限、題型預設與批次大小，一律依模式檔之「參數解析」節**，不得自行認定：純數字一律視為題數（不是條號章號）；題數未指定為 5、上限 20；題型未指定時依該科實際卷面（士全 4 科與師消防法規為測驗，師其餘 5 科為純申論卷故為申論）。參數：$ARGUMENTS

**`user-config-spec.md` 不為了取設定而 Read**——解析順序已寫在本檔，載入設定不需要該規格檔。但**這不代表整輪都不會讀它**：`weakness_tracking = "auto"` 時，出題當下就要寫 `pending` 斷點，屆時仍需其寫入 schema（**直接 `Read offset=87 limit=139` 一次取足，別先 Grep 定位**，見 exam-tutor SKILL.md 之「使用者設定」）。另外 **`pending` 非空時必須讀**該檔之「pending（未批改斷點）」與鐵則六：續作提示能顯示什麼、哪些欄位一律不得顯示，以該檔為準，不得憑印象續作。其餘情形（批改後要寫 `progress.json`、需跑初次詢問流程）才讀（見 exam-tutor SKILL.md 之「使用者設定」）。

---

**目前的 plugin 設定值**（Claude Code 於叫用本檔時代入；空白＝使用者未設定）：

- 應考等別 `level`：`${user_config.level}`
- 弱點記錄模式 `weakness_tracking`：`${user_config.weakness_tracking}`
- 學習資料目錄 `data_dir`：`${user_config.data_dir}`
- 本對話 ID（寫入 `pending.session_id` 用）：`${CLAUDE_SESSION_ID}`

上列即「設定解析順序」之順序 1，且**本檔是它唯一的代入點**——模式檔與 `user-config-spec.md` 是用 Read 讀入的一般檔案，其中的 `${user_config.*}` 不會被代入，不可把那裡看到的佔位符當成「未設定」。非空即採用、**不得再問一次**；空白才往下讀 `<data_dir>/config.json`。
