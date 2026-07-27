---
name: 抽考
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

---

**目前的 plugin 設定值**（Claude Code 於叫用本檔時代入；空白＝使用者未設定）：

- 應考等別 `level`：`${user_config.level}`
- 弱點記錄模式 `weakness_tracking`：`${user_config.weakness_tracking}`
- 學習資料目錄 `data_dir`：`${user_config.data_dir}`

上列即「設定解析順序」之順序 1，且**本檔是它唯一的代入點**——模式檔與 `user-config-spec.md` 是用 Read 讀入的一般檔案，其中的 `${user_config.*}` 不會被代入，不可把那裡看到的佔位符當成「未設定」。非空即採用、**不得再問一次**；空白才往下讀 `<data_dir>/config.json`。
