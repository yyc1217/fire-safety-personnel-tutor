# Changelog

本檔為**面向使用者的版本紀錄**（哪一版帶來什麼改變）。
維護者視角的完成項、決策紀錄與逐條轉寫更正明細見 [`docs/變更紀錄.md`](docs/變更紀錄.md)。

## 版本規則（重要）

`.claude-plugin/plugin.json` 的 `version` 是 Claude Code 判斷「使用者要不要更新」的**唯一依據**：
**只推 commit 不 bump 版本，已安裝的使用者收不到任何改變**，`/plugin update` 會回報「已是最新版本」。

因此：

> **凡異動 `skills/`、`reference/`、`corpus/`、`statutes/`，就必須 bump `plugin.json` 的 `version`（並同步 README 的 version badge）。**
> 這兩處是否一致由 CI（`scripts/ci_check_repo.py`）把關。

版號依 [semver](https://semver.org)：功能新增或行為改變 → MINOR；資料校正與文件修正 → PATCH。

---

## [0.10.0] - 2026-07-25

### 新增

- **導入 plugin `userConfig`**：應考等別、弱點記錄模式與學習資料目錄改為可在 Claude Code 的 `/plugin` 設定對話框直接填寫，值由 Claude Code 代入各 skill 內文（`${user_config.*}`），不必等到第一次對話才被問。
  - 三項來源的取用順序統一定義於 `reference/user-config-spec.md` 之「**設定解析順序**」：plugin 設定 → `<data_dir>/config.json` → 初次詢問流程。**既有使用者的 `config.json` 完全不受影響**，仍是第二順位且必須支援。
  - 留空即維持原本的互動式詢問（對話能說明師／士與三種記錄模式的差異，設定對話框做不到），故不對等別與記錄模式設預設值。
  - `exam_date`、`weekly_hours`、`progress_reminder` 仍只存 `config.json`——`exam_date` 需要「推算下一個六月第一個週六再請使用者確認」的互動，設定對話框無法勝任。
  - `/備考設定` 改為並列顯示兩處設定、標明何者生效，並明白告知**本指令改不動 plugin 設定**（該處要去 `/plugin` 改），不假裝寫入成功。

### 變更

- **`/出考卷` 改在獨立子代理中執行**（`context: fork` ＋ `background: false`）：整卷命題約需 5–8 分鐘、過程要翻大量條文與考古題，現在全部隔離在子代理裡，**只有完成的試卷回到主對話**。仍是同步等待（不改變「跑完才給你」的體感），但主對話不再被命題過程的中間讀取塞滿。
  - 代價誠實說明：子代理**看不到主對話歷史、也無法中途提問**。因此 `/出考卷` 未指定科目時不再詢問，改依「`$ARGUMENTS` → 讀書計畫下一個未完成單元 → 最弱考點 → 該等別最高頻科目」自行選定，並**於卷首說明選這科的理由**與如何指定科目。等別取不到時預設以「師」出卷並於卷首標明。
  - 在一般對話中說「出一份模擬考」走的仍是原路徑（不 fork），該詢問時照樣詢問。

- **`exam-tutor` 模式拆檔**：`SKILL.md` 一旦叫用就整份常駐 session，但其中六個模式彼此互斥——打 `/抽考` 卻要一併載入「整卷模擬考」與「申論擬答」的全部規範。現在 SKILL.md 只留**共用部分**（角色、資料來源、出題與批改主線、法條時效核對與條號要旨護欄、學習進度、優雅退場）＋**模式路由表**，六個模式移至 `skills/exam-tutor/modes/`，進入模式時才讀。SKILL.md 由 15,431 字降至 10,043 字（**−35%**），只用單一模式的指令不再載入其餘五個模式的規範。
  - 一併把原本只寫在「複習模式」段落、實際上「批改、申論擬答、弱點複習一體適用」的**條號要旨護欄**提升為 SKILL.md 的全模式共用規範。
  - `/抽考`、`/弱點複習`、`/掌握度`、`/申論猜題`、`/出考卷` 五個指令改為直接指向各自的模式檔。
  - CI 新增 `plugin-paths` 檢查：skill 內文引用的 `${CLAUDE_PLUGIN_ROOT}/...` 路徑須存在，且模式檔不得成為沒有任何路由指向的孤兒。

## [0.9.0] - 2026-07-25

發布層與 plugin 規格的體檢修正。**本版把 0.8.0 之後累積、但因未 bump 版本而未送達使用者的全部資料校正一併釋出**——主要是 `statutes/` 773 個檔案的品質修正（公式改 LaTeX、`²` 上標、階層編號拆行、編號括號全形、附檔名小寫、附圖歸位）。

### 新增

- 五個核心 skill 與十個 slash command skill 全面宣告 `allowed-tools`：查標籤索引（`jq`）、判讀原卷附圖（`pdftoppm`）與唯讀檔案存取不再反覆跳權限提示。**寫入使用者資料仍逐次徵詢同意**（`Write`／`Edit` 刻意不預先授權）。
- `jq` 未安裝時的降級路徑：各 skill 的「優雅退場」表新增以 `python3 -c` 取單鍵的等效作法，維持「只取所需單鍵、勿整檔載入」的鐵則；`pdftoppm` 缺席時改以文字描述附圖並附原卷頁碼，不杜撰圖形內容。
- CI（`.github/workflows/validate.yml`）：manifest 與版本一致性、skill frontmatter、`corpus/index.json` 160 卷路徑、960 條文件內部連結、上標與條文編號全形括號規範、法規版本時效，外加官方 `claude plugin validate --strict`。檢查邏輯在 `scripts/ci_check_repo.py`，可本機執行。
- `scripts/requirements.txt`：宣告 PyMuPDF／Pillow／numpy 與系統層 poppler-utils（**維護者專用，plugin 使用者不需安裝**）。
- README 新增「前置需求」與「安裝體積」說明（工作樹 142 MB，含 git 歷史首次下載約 265 MB）。
- `plugin.json`／`marketplace.json` 補 `keywords`、`category`、授權與作者資訊。

### 修正

- README 目錄結構誤植 slash command 數量（九 → 十）。
- README 授權說明改為**分離敘述**：程式碼與整理成果為 MIT；`corpus/`、`statutes/` 之官方原始資料不在 MIT 標的內，各依原出處條款。
- 維護者指令檔自 repo 根目錄移至 `.claude/CLAUDE.md`。兩個位置對 Claude Code 而言等價（同樣載入為專案脈絡），但放在 **plugin 根目錄**會被官方 `claude plugin validate` 判為無效內容（plugin 不透過 CLAUDE.md 提供脈絡，應用 skill）。移動後 `--strict` 驗證通過，維護者在本 repo 的開發脈絡不受影響。檔首並補上適用範圍說明。

## [0.8.0] - 2026-07-15

- 新增 `/掌握度`：以本機作答紀錄計算各主題／設備／法條之**內容覆蓋度**並畫成文字條圖表（唯讀，不寫檔）。
- `progress.json` 新增 `coverage` 結構，區分 `asked`（已問過）與 `done`（已展現掌握）。

## [0.7.0] - 2026-07-13

- 補齊 `reference/輸出格式/` 全套範本，各功能輸出版面改為「格式唯一真相、逐區塊比照」。

## [0.6.2] - 2026-07-13

- Plugin 體檢修正：卷型錯誤（師僅 5 科全申論、消防法規為混合卷）、猜題指令過時敘述、信心欄殘留與多處文件矛盾。

## [0.6.1] - 2026-07-11

- 修正 issue #14 測試回歸發現之缺陷。

## [0.6.0] - 2026-07-11

- 「熟悉法規」與「考前猜題」功能成形；猜題職責重構為**只產猜題範圍、不代為出題**。

---

更早的歷程（標籤系統建立、題庫品質校核、statutes 入庫）見 [`docs/變更紀錄.md`](docs/變更紀錄.md) 的「完成里程碑」。
