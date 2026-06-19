# fire-safety-personnel-tutor

消防設備師／士國家考試備考 Claude Code plugin：

- **`/fire-safety-personnel-tutor:exam-tutor`** — 家教模式：依考古題風格出題（頻率排序、單一設備連續提問、先問後等再解）、收作答、0–100 分批改，講解時引用法條全文（條／項／款／目階層）。
- **`/fire-safety-personnel-tutor:exam-trend-forecast`** — 考情分析：結合歷年考點分布與近 12–24 個月的法規修正、行政函令、重大時事，產出「法規脈動／技術實務／時事預測」三類趨勢報告（附依據與信心程度）。
- **`/fire-safety-personnel-tutor:exam-archive`** — 檔案庫查詢：列出題庫清單、提供指定年度科目的原卷 PDF、標準答案卷或單題原文。

所有內容與產出均為繁體中文。

## 安裝

```bash
claude plugin marketplace add https://github.com/yyc1217/fire-safety-engineer-tutor
claude plugin install fire-safety-personnel-tutor@fire-safety-personnel-tutor-marketplace
```

## 目錄結構

```
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── corpus/                  # 歷年考古題（唯讀資料，非 skill）
│   ├── index.json           # 全題庫入口（清單與中繼資料，含 等別 師/士）
│   ├── equipment_index.md   # 消防安全設備清單（單元邊界與頻率統計對照）
│   ├── INGEST.md            # 納入新年度題庫的人工流程
│   ├── md/                  # AI 讀取用之轉換文字（師/<年>/、士/<年>/）
│   └── pdf/                 # 原始 PDF：原卷＋答案卷（師/<年>/、士/<年>/）
├── statutes/                # 命題大綱法規現行全文 md（使用者手動整理）
│   └── index.md             # 法規清單、檔名對照與整理格式規範
└── skills/
    ├── exam-tutor/SKILL.md
    ├── exam-trend-forecast/SKILL.md
    └── exam-archive/SKILL.md
```

## 題庫現況

**設備師（師）**：民國 100–115 年六科、**設備士（士）**：100–115 年四科，原卷 PDF 與 md 均全數入庫。md 與 PDF 分置於 `corpus/md/` 與 `corpus/pdf/`。全庫共 3360 題，已逐題標籤（題型／系統／設備／法規／**條號**／知識領域／旗標），索引見 `corpus/tags_index.json`（產生器 `scripts/build_tags.py`，維度說明見 `docs/設計_題目標籤系統.md`）。

**法條**：命題大綱所列法規（`statutes/index.md` 第一～四節）已全數整理為現行全文 md。

## 資料準備

1. **考古題**：新增年度或士類試卷時，依 [`corpus/INGEST.md`](corpus/INGEST.md) 自考選部下載官方 PDF、轉成 md、更新 `corpus/index.json`。
2. **法條**：依 [`statutes/index.md`](statutes/index.md) 的清單與格式規範，自全國法規資料庫／消防署整理現行全文 md 放入 `statutes/`（命題大綱所列法規已全數入庫；附表附圖待人工核對項見 `docs/待核對清單.md`）。

skill 對 `corpus/` 與 `statutes/` 一律唯讀。學習進度紀錄存放於使用者自己的電腦（plugin 之外），位置與格式於執行時由使用者決定。

## 設計原則

- **以 corpus 取題型風格，以 statutes／即時搜尋取法源**：考古題只反映當年法規快照（`law_snapshot`），不可當現行法引用。
- **先問、後等、再解**：使用者作答前不給答案、不更新進度。
- **誠實性**：出題與批改前先自我驗證；趨勢預測附理由與信心程度，不呈現假確定。
- **優雅退場**：題庫未放入、法條缺漏、無網路等情況均降級運作並說明，缺條文且抓不到官方全文時停下求助。

## License

見 [LICENSE](LICENSE)。考古題為考選部公開資料；法條為公開法令。
