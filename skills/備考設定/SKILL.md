---
name: 備考設定
description: 設定或修改應考等別（師/士）、弱點記錄模式與資料目錄
argument-hint: [留空即互動式設定；或直接指定要改的項目，如：等別 士、記錄模式 none]
disable-model-invocation: true
allowed-tools:
  - Read
---
管理使用者設定。設定有**兩個存放處**，先讀 `${CLAUDE_PLUGIN_ROOT}/reference/user-config-spec.md` 的「**設定解析順序**」與「初次詢問流程」再動作。

**目前的 plugin 設定值**（由 Claude Code 代入；空白＝未設定）：

- 應考等別 `level`：`${user_config.level}`
- 弱點記錄模式 `weakness_tracking`：`${user_config.weakness_tracking}`
- 學習資料目錄 `data_dir`：`${user_config.data_dir}`

執行步驟：

1. **先顯示現值**：把上列 plugin 設定值與 `<data_dir>/config.json` 的內容並列給使用者看，標明**目前實際生效的是哪一個**（plugin 設定優先）。兩處不一致時明白指出。
2. **詢問要改哪些**：應考等別（消防設備師／消防設備士）、弱點記錄模式（自動記錄／產出筆記自行保存／不記錄，說明三者差異）、資料目錄。
3. **寫回**：本指令只能寫 `config.json`（`<data_dir>/config.json`，預設 `~/.fire-safety-tutor/`），並更新 `updated` 日期。
   **plugin 設定（`/plugin` 設定對話框）無法由本指令修改**——若某項目前由 plugin 設定生效，改 `config.json` 不會有效果。此時**告訴使用者要去 `/plugin` 找本 plugin 的設定對話框改**，或請他把該處清空以改用 `config.json`。不要假裝改成功了。
4. `exam_date`、`weekly_hours`、`progress_reminder` 只存在 `config.json`，本指令可直接改。

$ARGUMENTS
