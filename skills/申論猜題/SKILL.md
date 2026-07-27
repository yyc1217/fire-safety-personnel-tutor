---
description: 申論題猜題＋擬答：依猜題範圍或指定科目預測申論題目，附答題架構與擬答（每一論點附法源）
argument-hint: [科目或考點，如：消防法規、瓦斯漏氣警報；留空用最近一次猜題範圍]
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(jq *)
  - WebSearch
  - WebFetch
---
直接使用 **exam-tutor** skill 的「申論猜題＋擬答模式」，**產出預測題目＋答題架構＋擬答**。

**先讀 `${CLAUDE_PLUGIN_ROOT}/skills/exam-tutor/modes/申論猜題擬答.md`**（該檔為本模式規範唯一真相），再依其執行。

**本指令不是 `/猜題`**：不要改跑 exam-trend-forecast／`/猜題`，也**不得只輸出「猜題範圍」報告就停下、更不得叫使用者再呼叫一次 `/申論猜題`**。猜題範圍只是選題依據，本指令的交付物是「預測題目與擬答」。

**範圍來源**（依序取用，取到即開始擬答，不因缺猜題範圍而中止）：
1. `$ARGUMENTS` 指定之科目／考點（如「消防法規」）——直接以此為出題範圍。
2. 未指定時，沿用本 session 已產出之猜題範圍（exam-trend-forecast 結果）。
3. 仍無時，由 exam-tutor 依 `${CLAUDE_PLUGIN_ROOT}/corpus/tags_summary.json` 該等別加權頻率**就地選取高頻考點**作為範圍（輕量，**不執行 exam-trend-forecast 的完整 12–24 個月動態檢索**）。

**必產出**（依 exam-tutor「申論猜題＋擬答模式」規範）：預測題目（仿歷屆題型與配分，依 `level`）＋答題架構（破題→法源→分項論述→結論）＋擬答範例——每一論點附法源（法規名＋條項款＋版本日期，無法源之推論標注「非法源」）、**逐步推導**（要件→法源→涵攝→小結），計算題每步公式標明法源、代值附單位不跳步，直接寫結論不給高分。**版面一律依 `${CLAUDE_PLUGIN_ROOT}/reference/輸出格式/擬答格式.md` 逐區塊比照**（每題「題目→答題架構→擬答→本題法源清單」四區塊）。使用者同意時存 `<data_dir>/forecasts/申論猜題擬答_<等別><民國年>_<科目>.md`。

範圍：$ARGUMENTS

---

**目前的 plugin 設定值**（Claude Code 於叫用本檔時代入；空白＝使用者未設定）：

- 應考等別 `level`：`${user_config.level}`
- 弱點記錄模式 `weakness_tracking`：`${user_config.weakness_tracking}`
- 學習資料目錄 `data_dir`：`${user_config.data_dir}`

上列即「設定解析順序」之順序 1，且**本檔是它唯一的代入點**——模式檔與 `user-config-spec.md` 是用 Read 讀入的一般檔案，其中的 `${user_config.*}` 不會被代入，不可把那裡看到的佔位符當成「未設定」。非空即採用、**不得再問一次**；空白才往下讀 `<data_dir>/config.json`。
