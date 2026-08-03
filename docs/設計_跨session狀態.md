# 設計：跨 session 狀態（進度落地、續作斷點與併發）

> 對應版本 0.11.0。規格的**唯一真相**在 [`reference/user-config-spec.md`](../reference/user-config-spec.md)；
> 本檔記錄的是**為什麼這樣設計**與當初盤點出的問題，供日後改動時回頭對照。

## 起點：0.10.0 的跨 session 能力盤點

原設計把使用者資料落在 `data_dir`（預設 `~/.fire-safety-tutor/`），所以**檔案層本來就跨得過去**：

| 機制 | 位置 | 0.10.0 狀態 |
|------|------|-------------|
| 應考等別／記錄模式／資料目錄 | plugin `userConfig` ＋ `config.json` | ✅ 雙來源＋解析順序完整 |
| 作答與弱點 | `progress.json`（`attempts`／`asked_ids`／`weak_tally`／`coverage`） | ✅ auto 模式 |
| 讀書計畫 | `plans/讀書計畫_<等別><民國年>.md` | ✅ 明訂「跨對話讀回解析」 |
| 猜題／懶人包／筆記 | `forecasts/`、`notes/` | ✅ |
| 抽題去重、設備續問 | `asked_ids`、`coverage[設備].asked`／`next` | ✅ |

**跨不過去的是「對話狀態層」**，盤點出九項（依嚴重度）：

1. **未批改的那一題完全沒落地**——「先問、後等、再解」的等待狀態只存在對話脈絡。關掉視窗、`/clear`、脈絡壓縮、雲端 session 容器回收之後，新對話無從得知「上次問到哪一題、題目原文是什麼」。（改版前全 repo 只有兩處出現 `session`，且都指「本次對話內交棒」。）
2. **寫入時機是輪末而非逐題，且文件互相打架**——`exam-tutor/SKILL.md` 說批改時寫 `coverage`，`modes/弱點複習.md` 卻說「結束時總結；auto 模式寫回 progress.json」。一輪 5 題做到第 4 題中斷即整輪歸零。
3. **併發覆寫**——`progress.json` 單一 JSON 整檔重寫，無 lock、無 append-only、寫前不重讀。兩個視窗（或主對話與 `/fs-mock` 的 fork 子代理）同時寫，後者整檔蓋掉前者。
4. **沒有 `schema_version`**——spec 已有兩條遷移規則（`done`→`asked`、`total`→`points`），全靠「看到沒有 `asked` 欄就猜是舊檔」這種啟發式判斷。
5. **`attempts` 無界成長且要求整檔載入**——不像 `tags_index.json` 有「只取單鍵、勿整檔載入」的鐵則。練一年幾千題後，每個新對話一開場就吃掉大量脈絡。
6. **`/fs-mock` 的產出不落地**——`context: fork` 的子代理看不到主對話、也寫不回 `progress.json`，5–8 分鐘產的整卷關掉就沒了。
7. **`notes` 模式跨對話靠使用者手動回貼**——`notes/` 本來就在 `data_dir` 底下，其實可以自動讀回。
8. **雲端／遠端 session 根本不跨**——`~/.fire-safety-tutor` 在 Claude Code on the web 的容器裡是 ephemeral。
9. **寫入被拒絕時沒有規範**——「優雅退場」表列了 jq 缺席、PDF 缺失、無網路，就是沒列「使用者按了拒絕」，結果是使用者以為有記錄、實際沒有。

> **附帶澄清**：`Write` 不列入各 skill 的 `allowed-tools` **不會**擋掉寫檔。官方文件對該欄位的定義是
> 「Tools Claude can use **without asking permission** during the turn that invokes this skill」——那是預先授權，
> 限制用的是 `disallowed-tools`。所以「每次寫入都跳權限提示」是刻意設計（見 README 權限提示節），能力並未缺席。

## 0.11.0 做了什麼

**P0（止血）**

- `progress.json` 只留派生狀態（`asked_ids`／`weak_tally`／`coverage`／`pending`），逐題明細改存 **`attempts.jsonl`**（一題一行、只 append）。派生狀態全部可由 jsonl 重建。
- **寫入時機統一為逐題落地**：出題時寫斷點、每題批改完寫成績。刪掉 `modes/弱點複習.md` 的「結束時寫回」，輪末只做呈現。
- 加 **`schema_version`**（現行 3），把既有兩條遷移規則掛在版本號下，取代啟發式判斷。
- 每次寫 `progress.json` 前**先重讀再合併**，緩解多視窗互蓋。
- 「優雅退場」表補四列：拒絕寫入、斷點過期／等別不符、斷點屬另一視窗、進度檔損毀。

**P1（跨對話續作）**

- 新增 **`pending`** 斷點（未批改的題）與各出題 skill 的**續作偵測**六條規則。
- study-planner 的啟動進度報告加一句未完成題提示（只提示，不代為續作）。

## 關鍵取捨

### 一、`pending` 存題目全文，不只存 `q_id`

兩個候選：

- **A（採用）**：存 `question_text` 題目全文。
- **B**：只存 `q_id` ＋條號指標，新對話由 corpus 反查還原。

選 A 的理由是**本 plugin 有相當比例的題不是 corpus 原題**——`exam-tutor/SKILL.md` 明訂「考古題沒考過的條文再自行出題」，而 `reference/索引/設備條文索引.md` 的條文遠多於考古題覆蓋到的條文。方案 B 只有 `source: corpus` ＋ `variant: 原題不變更` 還原得了，改編題（類型 2）與自出題（類型 3）一律接不回來，正好在「逐條啃某個設備」這個最需要續作的場景失效。

成本是每題多存幾百字元，且批改完就從 `items` 移除。

### 二、斷點嚴禁含答案

`pending` 就在使用者自己的檔案系統裡，翻得到。因此規格明訂**不得寫入正解、評分要點、法源提示**，`articles` 欄雖存所考條號（供續作時對回索引）但**不得顯示給使用者**。這樣即使使用者去看檔案，看到的也只是自己剛才那一題，不牴觸「先問、後等、再解」。

### 三、`notes`／`none` 模式不支援續作

維持鐵則三（`none` 完全不寫任何檔案）與 `notes` 的「不寫 progress.json」語意，不為了續作破例。使用者問起時如實說明並告知可改用 `auto`。

### 四、併發只做「先重讀再合併」，不做 lock

檔案鎖需要 skill 端有可靠的原子操作與清理殘留鎖的機制，成本高於效益。實際情境是單人備考、偶爾開兩個視窗，因此：`attempts.jsonl` 用 append（最多損失當下一行）＋ `progress.json` 寫前重讀合併＋`session_id` 偵測 30 分鐘內的另一視窗並改為詢問。這組合把「整檔互蓋」降到「極少數欄位競態」。

## 尚未處理（後續版本）

- **`/fs-mock` 產出落地**：存 `<data_dir>/exams/`，並提供整卷回寫 `coverage` 的入口（原盤點第 6 項）。
- **`notes` 模式自動讀回**：弱點複習改為先 glob `<data_dir>/notes/*弱點筆記.md`，讀不到才請使用者提供（第 7 項）。
- **README 補「跨裝置／雲端使用」**：`data_dir` 指向雲端同步目錄的作法，以及 Claude Code on the web 為 ephemeral 容器、進度不保留的提醒（第 8 項）。
- **CI 檢查**：`progress.json` 欄位在 spec 與各 SKILL.md 間的一致性、防止「結束時才寫回」這類措辭回流。

---

*最後更新：2026-07-29*
