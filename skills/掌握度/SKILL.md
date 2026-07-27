---
description: 掌握度視覺化：把本機作答紀錄畫成各科目／主題／設備／法條的熟悉度文字條圖表，快速看出哪裡強、哪裡還沒碰
argument-hint: [可指定範圍，如「火災學」「水系統」「消防法規」或某設備]
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(jq *)
---
使用 exam-tutor skill 進入「掌握度視覺化模式」——**先讀 `${CLAUDE_PLUGIN_ROOT}/skills/exam-tutor/modes/掌握度視覺化.md`**（該檔為本模式規範唯一真相），再依其執行：先依 `${CLAUDE_PLUGIN_ROOT}/reference/user-config-spec.md` 載入設定與 `progress.json`，計算各主題／系統／設備／法條之**內容覆蓋度**（已展現掌握之內容點 ÷ 相關內容總點數；分母見 `reference/索引/火災學主題知識點索引.md`、`reference/索引/設備條文索引.md`、`statutes/`），再依 `${CLAUDE_PLUGIN_ROOT}/reference/輸出格式/掌握度圖表格式.md` 產出文字條圖表。本模式**唯讀**，不寫任何檔。範圍：$ARGUMENTS

---

**目前的 plugin 設定值**（Claude Code 於叫用本檔時代入；空白＝使用者未設定）：

- 應考等別 `level`：`${user_config.level}`
- 弱點記錄模式 `weakness_tracking`：`${user_config.weakness_tracking}`
- 學習資料目錄 `data_dir`：`${user_config.data_dir}`

上列即「設定解析順序」之順序 1，且**本檔是它唯一的代入點**——模式檔與 `user-config-spec.md` 是用 Read 讀入的一般檔案，其中的 `${user_config.*}` 不會被代入，不可把那裡看到的佔位符當成「未設定」。非空即採用、**不得再問一次**；空白才往下讀 `<data_dir>/config.json`。
