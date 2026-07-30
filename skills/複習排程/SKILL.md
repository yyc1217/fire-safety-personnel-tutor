---
name: 複習排程
description: 間隔重複複習：列出今天到期（含逾期）的考點，依記憶強度由弱到強逐項複習，答完自動算出下次該複習的日期
argument-hint: [可指定範圍，如某系統或科目；或 upcoming 看未來幾天排程]
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(jq *)
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/skills/spaced-repetition/cli.py"*)
---
使用 spaced-repetition skill——**先讀 `${CLAUDE_PLUGIN_ROOT}/skills/spaced-repetition/SKILL.md`**（該 skill 為本流程規範唯一真相），再依其執行：先依「設定解析順序」載入使用者設定（下列 plugin 設定 → `<data_dir>/config.json` → 初次詢問），跑 `cli.py init` 後以 `cli.py due` 取今日到期項目（已依 `ease_factor` 由低到高排序、附法規依據），逐項出題複習，批改後以 `cli.py record` 算回排程。範圍：$ARGUMENTS

出題、批改與引用條文的規範照 exam-tutor（含「先問、後等、再解」）；`weakness_tracking = "none"` 時不寫任何檔，改用試算並說明。**`reference/複習排程規格.md` 不在開場 Read**——需要精確的品質分數對映、`item_id` 命名或退場處置時才讀。

---

**目前的 plugin 設定值**（Claude Code 於叫用本檔時代入；空白＝使用者未設定）：

- 應考等別 `level`：`${user_config.level}`
- 弱點記錄模式 `weakness_tracking`：`${user_config.weakness_tracking}`
- 學習資料目錄 `data_dir`：`${user_config.data_dir}`

上列即「設定解析順序」之順序 1，且**本檔是它唯一的代入點**——`spaced-repetition/SKILL.md` 由本檔叫用時亦會代入，但 `user-config-spec.md`、`reference/複習排程規格.md` 是用 Read 讀入的一般檔案，其中的 `${user_config.*}` 不會被代入，不可把那裡看到的佔位符當成「未設定」。非空即採用、**不得再問一次**；空白才往下讀 `<data_dir>/config.json`。
