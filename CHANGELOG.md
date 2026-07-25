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
