---
name: fs-forecast
description: 【猜題】考前猜題：先秒回近10年加權頻率＋出題週期型態之統計結果（依考試科目分層、一問一答），詢問後才可選上網補修法/函令/時事動態
argument-hint: [可指定科目或範圍，留空分析全部]
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(jq *)
  - WebSearch
  - WebFetch
---
使用 exam-trend-forecast skill：先依 `${CLAUDE_PLUGIN_ROOT}/reference/user-config-spec.md` 依其「設定解析順序」載入應考等別，**輸出格式一律依 `${CLAUDE_PLUGIN_ROOT}/reference/輸出格式/猜題報告格式.md`（格式唯一真相），採兩段式**：

1. **第一段（一律先產出，皆本地、毋需上網）**：讀 `corpus/tags_summary.json` 建立近 10 年指數衰減加權頻率、讀 `corpus/tags_cycles.json` 取各考點出題週期型態（常年型／新興熱點／週期到期／冷卻中／一次性／偶發），依**考試科目分層**（師 6 科／士 4 科，只呈現本等別）產出統計結果：每科「猜題依據」總述＋具體考點 `###` 分節（一問一答：代表考古題＋條文全文）＋含測驗題科目附「測驗高頻數字」。**不露內部 tag 代碼、不列信心欄**（強弱由依據措辭表達）、全篇無 emoji。
2. **中段詢問**：問使用者要不要再上網補近 12–24 個月修法／函令／時事（約需 5–8 分鐘）；不需要就以第一段為最終輸出，頂端標注「未含近期動態」。
3. **第二段（使用者同意才執行）**：檢索官方來源三維度動態（修法與理由／函令與技術規範／重大時事），逐科併回「猜題依據」，頂端狀態改標「已含近 12–24 個月官方動態，資料截至 <YYYY-MM-DD>」（字串以 `reference/輸出格式/猜題報告格式.md` 為準）。

報告尾僅指路後續功能（/fs-essay、/fs-cram、/fs-plan），不代為執行。範圍：$ARGUMENTS

---

**目前的 plugin 設定值**（Claude Code 於叫用本檔時代入；空白＝使用者未設定）：

- 應考等別 `level`：`${user_config.level}`
- 弱點記錄模式 `weakness_tracking`：`${user_config.weakness_tracking}`
- 學習資料目錄 `data_dir`：`${user_config.data_dir}`

上列即「設定解析順序」之順序 1，且**本檔是它唯一的代入點**——模式檔與 `user-config-spec.md` 是用 Read 讀入的一般檔案，其中的 `${user_config.*}` 不會被代入，不可把那裡看到的佔位符當成「未設定」。非空即採用、**不得再問一次**；空白才往下讀 `<data_dir>/config.json`。
