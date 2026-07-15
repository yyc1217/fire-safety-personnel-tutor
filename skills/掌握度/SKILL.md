---
description: 掌握度視覺化：把本機作答紀錄畫成各科目／主題／設備／法條的熟悉度文字條圖表，快速看出哪裡強、哪裡還沒碰
argument-hint: [可指定範圍，如「火災學」「水系統」「消防法規」或某設備]
disable-model-invocation: true
---
使用 exam-tutor skill 進入「掌握度視覺化模式」：先依 `${CLAUDE_PLUGIN_ROOT}/reference/user-config-spec.md` 載入設定與 `progress.json`，計算各主題／系統／設備／法條之**內容覆蓋度**（已展現掌握之內容點 ÷ 相關內容總點數；分母見 `reference/火災學主題知識點索引.md`、`reference/設備條文索引.md`、`statutes/`），再依 `${CLAUDE_PLUGIN_ROOT}/reference/輸出格式/掌握度圖表格式.md` 產出文字條圖表。本模式**唯讀**，不寫任何檔。範圍：$ARGUMENTS
