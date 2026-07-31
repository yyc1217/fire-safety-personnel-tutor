---
name: 弱點複習
description: 考前弱點總複習：讀取作答紀錄中常錯的考點，優先重考與講解
argument-hint: [可指定範圍，如某系統或某設備]
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(jq *)
  - Bash(date *)
---
使用 exam-tutor skill 進入「弱點複習模式」——**先讀 `${CLAUDE_PLUGIN_ROOT}/skills/exam-tutor/modes/弱點複習.md`**（該檔為本模式規範唯一真相），再依其執行：先依 `${CLAUDE_PLUGIN_ROOT}/reference/user-config-spec.md` 載入使用者設定與 `progress.json` 之 `weak_tally`，按弱點嚴重程度選題重考。**開始選題前先跑「續作偵測」**：`weakness_tracking = "auto"` 時讀同檔之 `pending`，上次有沒批改完的題就先問要接續或重開（規則見同一份 spec 之「pending（未批改斷點）」）；成績與弱點**每題批改完立刻寫**，不累到輪末。範圍：$ARGUMENTS

---

**目前的 plugin 設定值**（Claude Code 於叫用本檔時代入；空白＝使用者未設定）：

- 應考等別 `level`：`${user_config.level}`
- 弱點記錄模式 `weakness_tracking`：`${user_config.weakness_tracking}`
- 學習資料目錄 `data_dir`：`${user_config.data_dir}`
- 本對話 ID（寫入 `pending.session_id` 用）：`${CLAUDE_SESSION_ID}`

上列即「設定解析順序」之順序 1，且**本檔是它唯一的代入點**——模式檔與 `user-config-spec.md` 是用 Read 讀入的一般檔案，其中的 `${user_config.*}` 不會被代入，不可把那裡看到的佔位符當成「未設定」。非空即採用、**不得再問一次**；空白才往下讀 `<data_dir>/config.json`。
