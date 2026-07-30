#!/usr/bin/env python3
"""間隔重複複習排程的 SQLite 儲存層。

排程演算法在 `scheduler.py`（純函式）；本檔只負責存取與遷移，
不重複實作任何演算法邏輯。介面層見 `cli.py`。

## 檔案位置（鐵則）

排程檔一律寫在**使用者的 `data_dir`** 之下（預設 `~/.fire-safety-tutor/review_schedule.db`），
**不寫進 plugin 目錄**——plugin 目錄唯讀（見 `reference/user-config-spec.md`「寫入邊界」），
且每次更新 plugin 都會被覆寫，排程放那裡等於隨時被清空。

## 為什麼用 SQLite 而不是併進 progress.json

排程的存取型態是「**只取今天到期的那幾列**」。SQL 一句
`WHERE next_review <= ? ORDER BY ease_factor` 就只回傳當天用得到的資料；
若併進 `progress.json`，每次都得把整份進度讀進脈絡才能篩，項目累積到數百筆後
會變成每輪固定的脈絡開銷。`progress.json` 仍是作答紀錄與掌握度的唯一來源，
本檔只存「什麼時候該再看一次」，兩者以 `item_id` 對齊、不重複存內容。

## 表結構（schema 唯一真相：reference/複習排程規格.md）

- `review_items`：每個知識點一列，存排程狀態與法規依據。
- `review_history`：每次作答一列（`review_items` 的明細），可回溯間隔怎麼長出來的。
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

import scheduler
from scheduler import ItemState, SchedulerError

#: 預設 data_dir（與 user-config-spec.md 一致）
DEFAULT_DATA_DIR = "~/.fire-safety-tutor"
#: 排程檔檔名
DB_FILENAME = "review_schedule.db"
#: 目前 schema 版本（存於 `PRAGMA user_version`）
SCHEMA_VERSION = 1

#: `item_id` 建議前綴：與 `corpus/tags_index.json` 及 `progress.json` 之
#: `weak_tally`／`coverage` 同一套 key，跨檔才對得上。不符者仍可存
#: （cli 會提醒），以免擋住合理的新型考點。
KNOWN_ITEM_PREFIXES = (
    "by_article:",
    "by_equipment:",
    "by_system:",
    "by_topic:",
    "by_law:",
    "延伸知識:",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_items (
    item_id       TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT '',
    category      TEXT NOT NULL DEFAULT '',
    citation      TEXT NOT NULL DEFAULT '',
    ease_factor   REAL NOT NULL DEFAULT 2.5,
    interval_days INTEGER NOT NULL DEFAULT 0,
    repetitions   INTEGER NOT NULL DEFAULT 0,
    last_reviewed TEXT,
    next_review   TEXT,
    created       TEXT NOT NULL,
    updated       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_due
    ON review_items (next_review, ease_factor);

CREATE TABLE IF NOT EXISTS review_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id       TEXT NOT NULL REFERENCES review_items (item_id) ON DELETE CASCADE,
    date          TEXT NOT NULL,
    result        TEXT NOT NULL,
    quality       INTEGER NOT NULL,
    interval_days INTEGER NOT NULL,
    ease_factor   REAL NOT NULL,
    q_id          TEXT,
    note          TEXT
);

CREATE INDEX IF NOT EXISTS idx_history_item
    ON review_history (item_id, date);
"""


class StorageError(RuntimeError):
    """資料庫層錯誤（找不到項目、schema 版本過新等）。"""


# --- 路徑 ---------------------------------------------------------------------


def resolve_data_dir(data_dir: str | None = None) -> Path:
    """決定 `data_dir`：參數 → `FIRE_SAFETY_DATA_DIR` 環境變數 → 預設值。

    設定的真正解析順序（plugin 設定 → `config.json` → 詢問）在 skill 內文執行，
    本檔只接收結果；環境變數是給 skill 傳值用的方便管道。
    """
    raw = data_dir or os.environ.get("FIRE_SAFETY_DATA_DIR") or DEFAULT_DATA_DIR
    return Path(raw).expanduser()


def default_db_path(data_dir: str | None = None) -> Path:
    return resolve_data_dir(data_dir) / DB_FILENAME


# --- 連線與遷移 ---------------------------------------------------------------


def init_db(db_path: str | Path) -> Path:
    """建立（或升級）排程檔並回傳其路徑。可重複執行，冪等。"""
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path, create=True) as conn:
        migrate(conn)
    return path


@contextmanager
def connect(db_path: str | Path, *, create: bool = False) -> Iterator[sqlite3.Connection]:
    """開啟連線；離開時成功即 commit、拋錯即 rollback。

    `create=False` 且檔案不存在時拋 `StorageError`——排程檔不該被意外建在
    打錯的路徑上（例如 `data_dir` 解析失敗時的相對路徑）。
    """
    path = Path(db_path).expanduser()
    if not path.exists() and not create:
        raise StorageError(
            f"找不到排程檔：{path}（尚未建立？先執行 `cli.py init`）"
        )
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate(conn: sqlite3.Connection) -> int:
    """把 schema 帶到 `SCHEMA_VERSION`，回傳遷移後的版本。

    新增欄位時的作法：把 `ALTER TABLE` 寫成新的 `if version < N` 區塊、
    `SCHEMA_VERSION` 加一；舊檔開啟時自動補上，不需使用者手動處理。
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise StorageError(
            f"排程檔 schema 版本 {version} 高於本程式支援的 {SCHEMA_VERSION}："
            "請更新 plugin，或改用較新版本開啟，勿以舊版寫入以免資料遺失。"
        )
    if version < 1:
        conn.executescript(_SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return SCHEMA_VERSION


# --- 讀取 ---------------------------------------------------------------------


def _state_of(row: Mapping[str, Any]) -> ItemState:
    """由 `review_items` 的一列（Row 或 dict）取出排程狀態。"""
    return ItemState(
        ease_factor=row["ease_factor"],
        interval_days=row["interval_days"],
        repetitions=row["repetitions"],
        last_reviewed=row["last_reviewed"],
        next_review=row["next_review"],
    )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def get_item(
    conn: sqlite3.Connection, item_id: str, *, with_history: bool = False
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM review_items WHERE item_id = ?", (item_id,)
    ).fetchone()
    if row is None:
        return None
    item = _row_to_dict(row)
    if with_history:
        item["history"] = history(conn, item_id)
    return item


def history(
    conn: sqlite3.Connection, item_id: str, *, limit: int | None = None
) -> list[dict[str, Any]]:
    sql = (
        "SELECT date, result, quality, interval_days, ease_factor, q_id, note "
        "FROM review_history WHERE item_id = ? ORDER BY date, id"
    )
    params: list[Any] = [item_id]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [_row_to_dict(r) for r in conn.execute(sql, params)]


def due_items(
    conn: sqlite3.Connection,
    today: date | str,
    *,
    limit: int | None = None,
    category: str | None = None,
    include_new: bool = True,
) -> list[dict[str, Any]]:
    """今日（含逾期）到期項目，**依 ease_factor 由低到高**（最弱的先複習）。

    同 ease 者以 `next_review` 早者優先（逾期越久越前面），再以 `item_id` 定序，
    確保同一天多次呼叫順序一致。`include_new`：`next_review` 為空的新項目
    （剛加入、還沒答過）視為到期。
    """
    today_iso = scheduler.parse_date(today).isoformat()
    where = ["(next_review IS NOT NULL AND next_review <= ?)"]
    params: list[Any] = [today_iso]
    if include_new:
        where.append("next_review IS NULL")
    # 附上「上次結果」：介面要顯示「上次答錯」才看得出為什麼這項排在前面。
    sql = (
        "SELECT *, ("
        "  SELECT h.result FROM review_history h WHERE h.item_id = review_items.item_id"
        "  ORDER BY h.date DESC, h.id DESC LIMIT 1"
        ") AS last_result "
        f"FROM review_items WHERE ({' OR '.join(where)})"
    )
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY ease_factor ASC, next_review ASC, item_id ASC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [_row_to_dict(r) for r in conn.execute(sql, params)]


def upcoming_items(
    conn: sqlite3.Connection, today: date | str, *, days: int = 7
) -> list[dict[str, Any]]:
    """未來 `days` 天內即將到期者（不含今日到期），供「本週預覽」。"""
    start = scheduler.parse_date(today)
    end = start + timedelta(days=days)
    return [
        _row_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM review_items WHERE next_review > ? AND next_review <= ? "
            "ORDER BY next_review ASC, ease_factor ASC",
            (start.isoformat(), end.isoformat()),
        )
    ]


def all_items(
    conn: sqlite3.Connection, *, category: str | None = None
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM review_items"
    params: list[Any] = []
    if category:
        sql += " WHERE category = ?"
        params.append(category)
    sql += " ORDER BY ease_factor ASC, item_id ASC"
    return [_row_to_dict(r) for r in conn.execute(sql, params)]


def stats(conn: sqlite3.Connection, today: date | str) -> dict[str, Any]:
    """總覽數字：總數、今日到期、未排程、各分類、最弱五項、正確率。"""
    today_iso = scheduler.parse_date(today).isoformat()
    total = conn.execute("SELECT COUNT(*) FROM review_items").fetchone()[0]
    due = conn.execute(
        "SELECT COUNT(*) FROM review_items "
        "WHERE next_review IS NULL OR next_review <= ?",
        (today_iso,),
    ).fetchone()[0]
    overdue = conn.execute(
        "SELECT COUNT(*) FROM review_items WHERE next_review IS NOT NULL "
        "AND next_review < ?",
        (today_iso,),
    ).fetchone()[0]
    by_category = {
        r["category"] or "（未分類）": r["n"]
        for r in conn.execute(
            "SELECT category, COUNT(*) AS n FROM review_items "
            "GROUP BY category ORDER BY n DESC, category"
        )
    }
    weakest = [
        _row_to_dict(r)
        for r in conn.execute(
            "SELECT item_id, title, category, citation, ease_factor, next_review "
            "FROM review_items ORDER BY ease_factor ASC, item_id ASC LIMIT 5"
        )
    ]
    reviews, correct = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(result = 'correct'), 0) FROM review_history"
    ).fetchone()
    return {
        "as_of": today_iso,
        "total_items": total,
        "due_today": due,
        "overdue": overdue,
        "by_category": by_category,
        "weakest": weakest,
        "reviews_logged": reviews,
        "correct_rate": round(correct / reviews, 3) if reviews else None,
    }


# --- 寫入 ---------------------------------------------------------------------


def normalize_item_id(item_id: str) -> str:
    """去空白並驗證非空。

    `item_id` 格式：`<tag key>` 或 `<tag key>#<要點名>`（細到單一要點時用）。
    `#` 前一段必須是可對回 `tags_index.json` 的 key，才能反查考古題出題。
    """
    cleaned = (item_id or "").strip()
    if not cleaned:
        raise SchedulerError("item_id 不得為空")
    return cleaned


def base_tag(item_id: str) -> str:
    """取 `item_id` 的 tag key 部分（去掉 `#<要點名>`），用於反查 tags_index。"""
    return normalize_item_id(item_id).split("#", 1)[0]


def has_known_prefix(item_id: str) -> bool:
    return base_tag(item_id).startswith(KNOWN_ITEM_PREFIXES)


def add_item(
    conn: sqlite3.Connection,
    item_id: str,
    *,
    title: str = "",
    category: str = "",
    citation: str = "",
    today: date | str | None = None,
) -> dict[str, Any]:
    """新增項目，或補上既有項目的描述欄位（**不動排程狀態**）。

    描述欄位以「有給值才覆寫」處理：批改流程常常只帶得出 `citation`，
    不該因此把先前存好的 `title` 清成空字串。
    """
    item_id = normalize_item_id(item_id)
    stamp = scheduler.parse_date(today or date.today()).isoformat()
    existing = get_item(conn, item_id)
    if existing is None:
        conn.execute(
            "INSERT INTO review_items "
            "(item_id, title, category, citation, ease_factor, interval_days, "
            " repetitions, last_reviewed, next_review, created, updated) "
            "VALUES (?, ?, ?, ?, ?, 0, 0, NULL, NULL, ?, ?)",
            (
                item_id,
                title,
                category,
                citation,
                scheduler.DEFAULT_EASE_FACTOR,
                stamp,
                stamp,
            ),
        )
    else:
        conn.execute(
            "UPDATE review_items SET title = ?, category = ?, citation = ?, "
            "updated = ? WHERE item_id = ?",
            (
                title or existing["title"],
                category or existing["category"],
                citation or existing["citation"],
                stamp,
                item_id,
            ),
        )
    item = get_item(conn, item_id)
    assert item is not None  # 剛寫入，必存在
    return item


def record_review(
    conn: sqlite3.Connection,
    item_id: str,
    quality: int,
    *,
    today: date | str | None = None,
    title: str = "",
    category: str = "",
    citation: str = "",
    q_id: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """記一次複習結果，更新排程並寫入 history。項目不存在時自動建立。

    回傳更新後的項目（含 `previous` 區塊，供介面顯示「間隔怎麼變的」）。
    """
    item_id = normalize_item_id(item_id)
    scheduler.validate_quality(quality)
    day = scheduler.parse_date(today or date.today())

    before = add_item(
        conn,
        item_id,
        title=title,
        category=category,
        citation=citation,
        today=day,
    )
    old_state = _state_of(before)
    new_state = scheduler.review(old_state, quality, day)

    conn.execute(
        "UPDATE review_items SET ease_factor = ?, interval_days = ?, repetitions = ?, "
        "last_reviewed = ?, next_review = ?, updated = ? WHERE item_id = ?",
        (
            new_state.ease_factor,
            new_state.interval_days,
            new_state.repetitions,
            new_state.last_reviewed,
            new_state.next_review,
            day.isoformat(),
            item_id,
        ),
    )
    conn.execute(
        "INSERT INTO review_history "
        "(item_id, date, result, quality, interval_days, ease_factor, q_id, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item_id,
            day.isoformat(),
            "correct" if quality >= scheduler.PASSING_QUALITY else "wrong",
            quality,
            new_state.interval_days,
            new_state.ease_factor,
            q_id,
            note,
        ),
    )
    item = get_item(conn, item_id)
    assert item is not None
    item["previous"] = {
        "ease_factor": old_state.ease_factor,
        "interval_days": old_state.interval_days,
        "repetitions": old_state.repetitions,
        "last_reviewed": old_state.last_reviewed,
        "next_review": old_state.next_review,
        "is_new": before["last_reviewed"] is None,
    }
    return item


def preview_review(
    conn: sqlite3.Connection | None,
    item_id: str,
    quality: int,
    *,
    today: date | str | None = None,
) -> dict[str, Any]:
    """試算：若此刻以 `quality` 作答，排程會變成什麼——**不寫任何資料**。

    供 `weakness_tracking = "none"`／使用者不願建排程檔時仍能說明
    「答對的話下次何時複習」，以及答題前的說明用。`conn` 為 None 時
    以全新項目試算。
    """
    scheduler.validate_quality(quality)
    day = scheduler.parse_date(today or date.today())
    row = (
        conn.execute("SELECT * FROM review_items WHERE item_id = ?", (item_id,)).fetchone()
        if conn is not None
        else None
    )
    old_state = _state_of(row) if row is not None else ItemState()
    new_state = scheduler.review(old_state, quality, day)
    return {
        "item_id": normalize_item_id(item_id),
        "quality": quality,
        "before": {
            "ease_factor": old_state.ease_factor,
            "interval_days": old_state.interval_days,
            "repetitions": old_state.repetitions,
            "next_review": old_state.next_review,
        },
        "after": {
            "ease_factor": new_state.ease_factor,
            "interval_days": new_state.interval_days,
            "repetitions": new_state.repetitions,
            "next_review": new_state.next_review,
        },
        "dry_run": True,
    }


def reset_item(
    conn: sqlite3.Connection, item_id: str, *, keep_history: bool = True
) -> dict[str, Any]:
    """把項目打回未學狀態（ease 2.5、間隔 0、次數 0），保留描述欄位。"""
    item_id = normalize_item_id(item_id)
    if get_item(conn, item_id) is None:
        raise StorageError(f"排程中沒有這個項目：{item_id}")
    conn.execute(
        "UPDATE review_items SET ease_factor = ?, interval_days = 0, repetitions = 0, "
        "last_reviewed = NULL, next_review = NULL, updated = ? WHERE item_id = ?",
        (scheduler.DEFAULT_EASE_FACTOR, date.today().isoformat(), item_id),
    )
    if not keep_history:
        conn.execute("DELETE FROM review_history WHERE item_id = ?", (item_id,))
    item = get_item(conn, item_id)
    assert item is not None
    return item


def delete_item(conn: sqlite3.Connection, item_id: str) -> bool:
    """刪除項目與其歷史；回傳是否真的刪到東西。"""
    cur = conn.execute(
        "DELETE FROM review_items WHERE item_id = ?", (normalize_item_id(item_id),)
    )
    return cur.rowcount > 0


def import_items(
    conn: sqlite3.Connection, items: Iterable[dict[str, Any]], *, today: date | str | None = None
) -> int:
    """批次加入項目（只建描述、不排程），回傳新增或更新的筆數。"""
    count = 0
    for raw in items:
        add_item(
            conn,
            raw["item_id"],
            title=raw.get("title", ""),
            category=raw.get("category", ""),
            citation=raw.get("citation", ""),
            today=today,
        )
        count += 1
    return count


def to_json_record(conn: sqlite3.Connection, item_id: str) -> dict[str, Any] | None:
    """輸出單一項目的完整 JSON（含 history），欄位順序即規格文件所列。"""
    item = get_item(conn, item_id, with_history=True)
    if item is None:
        return None
    return {
        "item_id": item["item_id"],
        "title": item["title"],
        "category": item["category"],
        "citation": item["citation"],
        "ease_factor": item["ease_factor"],
        "interval_days": item["interval_days"],
        "repetitions": item["repetitions"],
        "last_reviewed": item["last_reviewed"],
        "next_review": item["next_review"],
        "history": [
            {
                "date": h["date"],
                "result": h["result"],
                "quality": h["quality"],
                "interval_days": h["interval_days"],
                "ease_factor": h["ease_factor"],
                **({"q_id": h["q_id"]} if h["q_id"] else {}),
                **({"note": h["note"]} if h["note"] else {}),
            }
            for h in item["history"]
        ],
    }
