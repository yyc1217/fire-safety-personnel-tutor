# fire-safety-personnel-tutor

消防設備師／士國家考試備考 Claude Code plugin：

- **exam-tutor** — 家教模式：以消防安全設備為主體、依 `reference/設備條文索引.md` 課綱地圖連續出題（先問後等再解）、收作答、0–100 分批改，講解時引用法條全文（條／項／款／目階層）；含快速抽考（3~5 題）與弱點複習模式。
- **exam-trend-forecast** — 考情分析與猜題：結合近 10 年加權考點分布與近 12–24 個月的法規修正、行政函令、重大時事，產出「法規脈動／技術實務／時事預測」趨勢報告（附依據與信心程度），並可延伸四種產出：直接練（交棒 exam-tutor）、可勾銷猜題清單、申論猜題＋擬答、考前必背懶人包。
- **statute-memorizer** — 法規記憶助手：整理易混淆數字／時限／罰則成記憶卡與口訣、產生跨法規對照表（內建 8 張高頻對照表＋即時生成）。
- **exam-archive** — 檔案庫查詢：列出題庫清單、提供指定年度科目的原卷 PDF、標準答案卷或單題原文。

### Slash commands

| 指令 | 功能 |
|------|------|
| `/抽考 [範圍]` | 快速抽考一輪 3~5 題（零碎時間用） |
| `/弱點複習 [範圍]` | 依作答紀錄優先重考常錯考點 |
| `/記憶重點 <主題>` | 整理記憶卡／口訣／易混淆組 |
| `/對照表 [主題]` | 跨法規對照表（留空列出內建清單） |
| `/猜題 [範圍]` | 完整猜題流程＋四種後續產出 |
| `/懶人包 [範圍]` | 考前必背懶人包 |
| `/申論猜題 [科目]` | 申論題猜題＋答題架構＋擬答 |
| `/設定` | 設定應考等別（師/士）、弱點記錄模式 |

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
├── reference/               # 內建整理資產（唯讀）
│   ├── index.md             # 資產索引與「內建優先、即時補充」原則
│   ├── user-config-spec.md  # 使用者設定/進度檔共用規格（各 skill 引用）
│   ├── 設備條文索引.md       # 設備×條文課綱地圖（exam-tutor 連續出題依據）
│   └── 對照表/              # 8 張高頻考點對照表（檢修申報、水系統數值…）
├── commands/                # slash commands（/抽考、/猜題、/設定 等 8 個）
└── skills/
    ├── exam-tutor/SKILL.md
    ├── exam-trend-forecast/SKILL.md
    ├── statute-memorizer/SKILL.md
    └── exam-archive/SKILL.md
```

## 題庫現況

**設備師（師）**：民國 100–115 年六科、**設備士（士）**：100–115 年四科，原卷 PDF 與 md 均全數入庫。md 與 PDF 分置於 `corpus/md/` 與 `corpus/pdf/`。全庫共 3360 題，已逐題標籤（題型／系統／設備／法規／**條號**／知識領域／旗標），索引見 `corpus/tags_index.json`（產生器 `scripts/build_tags.py`，維度說明見 `docs/設計_題目標籤系統.md`）。

**法條**：命題大綱所列法規（`statutes/index.md` 第一～四節）已全數整理為現行全文 md。

## 資料準備

1. **考古題**：新增年度或士類試卷時，依 [`corpus/INGEST.md`](corpus/INGEST.md) 自考選部下載官方 PDF、轉成 md、更新 `corpus/index.json`。
2. **法條**：依 [`statutes/index.md`](statutes/index.md) 的清單與格式規範，自全國法規資料庫／消防署整理現行全文 md 放入 `statutes/`（命題大綱所列法規已全數入庫並完成人工核對；各檔檔首附「📌 免責聲明」，引用前請依官方公告核對）。

skill 對 `corpus/`、`statutes/` 與 `reference/` 一律唯讀。使用者設定（應考等別、弱點記錄模式）與學習進度存放於使用者自己的電腦（預設 `~/.fire-safety-tutor/`，plugin 之外），初次使用時詢問一次並記住；規格見 [`reference/user-config-spec.md`](reference/user-config-spec.md)。

## 設計原則

- **以 corpus 取題型風格，以 statutes／即時搜尋取法源**：考古題只反映當年法規快照（`law_snapshot`），不可當現行法引用。
- **先問、後等、再解**：使用者作答前不給答案、不更新進度。
- **誠實性**：出題與批改前先自我驗證；趨勢預測附理由與信心程度，不呈現假確定。
- **優雅退場**：題庫未放入、法條缺漏、無網路等情況均降級運作並說明，缺條文且抓不到官方全文時停下求助。

## License

見 [LICENSE](LICENSE)。考古題為考選部公開資料；法條為公開法令。
