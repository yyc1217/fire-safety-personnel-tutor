---
description: 快速抽考一輪 3~5 題，適合零碎時間複習（可指定系統/設備/科目/題數）
argument-hint: [範圍或題數，留空則依弱點與頻率自動選]
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(jq *)
---
使用 exam-tutor skill 進入「快速抽考模式」——**先讀 `${CLAUDE_PLUGIN_ROOT}/skills/exam-tutor/modes/快速抽考.md`**（該檔為本模式規範唯一真相），再依其執行：先依 `${CLAUDE_PLUGIN_ROOT}/reference/user-config-spec.md` 依其「設定解析順序」載入使用者設定（plugin 設定 → config.json → 初次詢問），一輪出 3~5 題、快節奏一題一答一講。範圍：$ARGUMENTS
