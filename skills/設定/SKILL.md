---
description: 設定或修改應考等別（師/士）、弱點記錄模式與資料目錄
argument-hint: [留空即互動式設定；或直接指定要改的項目，如：等別 士、記錄模式 none]
disable-model-invocation: true
---
依 `${CLAUDE_PLUGIN_ROOT}/reference/user-config-spec.md` 的「初次詢問流程」重跑設定：詢問應考等別（消防設備師／消防設備士）與弱點記錄模式（自動記錄／產出筆記自行保存／不記錄），更新使用者 `config.json`（預設位置 `~/.fire-safety-tutor/`，可改）。若已有設定檔，先顯示現值再詢問要改哪些。$ARGUMENTS
