---
name: 懶人包
description: 考前必背懶人包：猜題範圍＋平時弱點濃縮成必背條文重點＋記憶術一份文件
argument-hint: [可指定考點數量或科目，預設前 20 個考點]
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(jq *)
---
使用 statute-memorizer skill 產出「考前必背懶人包」：合成三個來源——猜題範圍（exam-trend-forecast 之結果，無則依該等別加權頻率前 N 名）、**平時弱點**（`progress.json` 之 `weak_tally`，常錯考點一律納入並標注「⚠ 你的弱點」且排序優先）、內建對照表（`${CLAUDE_PLUGIN_ROOT}/reference/對照表/`）——濃縮為考點→必背條文重點→修法新點→記憶術，**版面一律依 `${CLAUDE_PLUGIN_ROOT}/reference/輸出格式/懶人包格式.md` 逐區塊比照**（科目分節、弱點排最前、必背一行一事實附法源）。完成後詢問是否存入 `<data_dir>/forecasts/`。範圍：$ARGUMENTS

---

**目前的 plugin 設定值**（Claude Code 於叫用本檔時代入；空白＝使用者未設定）：

- 應考等別 `level`：`${user_config.level}`
- 弱點記錄模式 `weakness_tracking`：`${user_config.weakness_tracking}`
- 學習資料目錄 `data_dir`：`${user_config.data_dir}`

上列即「設定解析順序」之順序 1，且**本檔是它唯一的代入點**——模式檔與 `user-config-spec.md` 是用 Read 讀入的一般檔案，其中的 `${user_config.*}` 不會被代入，不可把那裡看到的佔位符當成「未設定」。非空即採用、**不得再問一次**；空白才往下讀 `<data_dir>/config.json`。
