"""`skills/spaced-repetition/storage.py` 的單元測試（每個測試用獨立臨時 DB）。"""

from __future__ import annotations

import sqlite3

import pytest

import scheduler
import storage
from storage import StorageError

TODAY = "2026-07-30"

ITEM = dict(
    item_id="by_article:設置標準第82條#藥劑保持時間",
    title="CO₂ 藥劑保持時間計算",
    category="化學系統",
    citation="各類場所消防安全設備設置標準 §82",
)


@pytest.fixture()
def db(tmp_path):
    return storage.init_db(tmp_path / "review_schedule.db")


@pytest.fixture()
def conn(db):
    with storage.connect(db) as c:
        yield c


# --- 建檔與遷移 ---------------------------------------------------------------


def test_init_db_creates_file_and_parent_dirs(tmp_path):
    path = storage.init_db(tmp_path / "巢狀" / "目錄" / storage.DB_FILENAME)
    assert path.exists()


def test_init_db_is_idempotent(tmp_path):
    path = tmp_path / storage.DB_FILENAME
    storage.init_db(path)
    with storage.connect(path) as c:
        storage.record_review(c, "by_topic:燃燒理論", 4, today=TODAY)
    storage.init_db(path)  # 再跑一次不得清資料
    with storage.connect(path) as c:
        assert storage.get_item(c, "by_topic:燃燒理論") is not None


def test_schema_version_recorded(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == storage.SCHEMA_VERSION


def test_newer_schema_is_refused_rather_than_downgraded(conn):
    conn.execute("PRAGMA user_version = 99")
    with pytest.raises(StorageError, match="高於本程式支援"):
        storage.migrate(conn)


def test_connect_refuses_to_create_by_accident(tmp_path):
    with pytest.raises(StorageError, match="找不到排程檔"):
        with storage.connect(tmp_path / "不存在.db"):
            pass


def test_connect_rolls_back_on_error(db):
    with pytest.raises(RuntimeError):
        with storage.connect(db) as c:
            storage.add_item(c, "by_equipment:滅火器", today=TODAY)
            raise RuntimeError("中途失敗")
    with storage.connect(db) as c:
        assert storage.get_item(c, "by_equipment:滅火器") is None


def test_history_is_removed_with_its_item(conn):
    storage.record_review(conn, "by_equipment:滅火器", 4, today=TODAY)
    assert storage.delete_item(conn, "by_equipment:滅火器") is True
    assert conn.execute("SELECT COUNT(*) FROM review_history").fetchone()[0] == 0


# --- 描述欄位 -----------------------------------------------------------------


def test_add_item_starts_unscheduled_and_therefore_due(conn):
    item = storage.add_item(conn, **ITEM, today=TODAY)
    assert item["next_review"] is None
    assert item["ease_factor"] == scheduler.DEFAULT_EASE_FACTOR
    assert [i["item_id"] for i in storage.due_items(conn, TODAY)] == [ITEM["item_id"]]


def test_add_item_does_not_blank_existing_metadata(conn):
    storage.add_item(conn, **ITEM, today=TODAY)
    again = storage.add_item(conn, ITEM["item_id"], citation="改過的依據", today=TODAY)
    assert again["title"] == ITEM["title"]  # 沒給就保留
    assert again["citation"] == "改過的依據"  # 給了就覆寫


def test_add_item_does_not_touch_schedule(conn):
    storage.record_review(conn, ITEM["item_id"], 4, today=TODAY, **_meta())
    storage.add_item(conn, ITEM["item_id"], title="換個標題", today=TODAY)
    item = storage.get_item(conn, ITEM["item_id"])
    assert item["repetitions"] == 1
    assert item["next_review"] == "2026-07-31"


def _meta():
    return {k: v for k, v in ITEM.items() if k != "item_id"}


def test_empty_item_id_rejected(conn):
    with pytest.raises(scheduler.SchedulerError):
        storage.add_item(conn, "   ", today=TODAY)


def test_base_tag_strips_sub_point():
    assert storage.base_tag(ITEM["item_id"]) == "by_article:設置標準第82條"
    assert storage.has_known_prefix(ITEM["item_id"]) is True
    assert storage.has_known_prefix("co2_hold_time_calc") is False


# --- 記錄複習 -----------------------------------------------------------------


def test_record_review_creates_item_on_the_fly(conn):
    item = storage.record_review(conn, ITEM["item_id"], 4, today=TODAY, **_meta())
    assert item["citation"] == ITEM["citation"]
    assert item["previous"]["is_new"] is True
    assert item["interval_days"] == 1
    assert item["next_review"] == "2026-07-31"


def test_record_review_persists_scheduler_output(conn):
    storage.record_review(conn, "by_topic:閃燃", 4, today="2026-07-30")
    storage.record_review(conn, "by_topic:閃燃", 4, today="2026-07-31")
    item = storage.record_review(conn, "by_topic:閃燃", 4, today="2026-08-06")
    assert (item["repetitions"], item["interval_days"]) == (3, 15)
    assert item["next_review"] == "2026-08-21"
    assert item["previous"]["interval_days"] == 6


def test_record_review_appends_history(conn):
    storage.record_review(conn, "by_topic:閃燃", 4, today="2026-07-30", q_id="師/113/0806#3")
    storage.record_review(conn, "by_topic:閃燃", 1, today="2026-07-31", note="混淆了")
    rows = storage.history(conn, "by_topic:閃燃")
    assert [r["result"] for r in rows] == ["correct", "wrong"]
    assert [r["quality"] for r in rows] == [4, 1]
    assert rows[0]["q_id"] == "師/113/0806#3"
    assert rows[1]["note"] == "混淆了"


def test_record_review_rejects_bad_quality(conn):
    with pytest.raises(scheduler.SchedulerError):
        storage.record_review(conn, "by_topic:閃燃", 9, today=TODAY)
    assert storage.get_item(conn, "by_topic:閃燃") is None  # 不得留下半筆資料


def test_history_survives_a_lapse_for_later_diagnosis(conn):
    for day, quality in [("2026-07-30", 4), ("2026-07-31", 4), ("2026-08-06", 0)]:
        storage.record_review(conn, "by_equipment:滅火器", quality, today=day)
    item = storage.get_item(conn, "by_equipment:滅火器")
    assert (item["repetitions"], item["interval_days"]) == (0, 1)
    assert len(storage.history(conn, "by_equipment:滅火器")) == 3


# --- 到期查詢與排序 -----------------------------------------------------------


def _seed(conn):
    """三項：ease 由低到高，到期日不同。"""
    rows = [
        ("by_article:設置標準第82條", "CO₂ 保持時間", 1.4, "2026-07-27"),
        ("by_article:設置標準第126條", "P 型受信總機分區上限", 1.8, "2026-07-30"),
        ("by_equipment:滅火器", "滅火器設置", 2.5, "2026-08-10"),
    ]
    for item_id, title, ease, next_review in rows:
        storage.add_item(conn, item_id, title=title, category="測試", today=TODAY)
        conn.execute(
            "UPDATE review_items SET ease_factor = ?, next_review = ?, "
            "last_reviewed = ?, interval_days = 3, repetitions = 1 WHERE item_id = ?",
            (ease, next_review, "2026-07-24", item_id),
        )


def test_due_items_sorted_by_ease_ascending(conn):
    _seed(conn)
    due = storage.due_items(conn, TODAY)
    assert [d["title"] for d in due] == ["CO₂ 保持時間", "P 型受信總機分區上限"]
    assert due[0]["ease_factor"] < due[1]["ease_factor"]


def test_due_items_includes_overdue_but_not_future(conn):
    _seed(conn)
    assert len(storage.due_items(conn, TODAY)) == 2
    assert len(storage.due_items(conn, "2026-08-10")) == 3


def test_due_items_tie_break_is_deterministic(conn):
    for item_id in ("b", "a", "c"):
        storage.add_item(conn, f"by_topic:{item_id}", today=TODAY)
        conn.execute(
            "UPDATE review_items SET ease_factor = 2.0, next_review = ?, "
            "last_reviewed = ? WHERE item_id = ?",
            (TODAY, TODAY, f"by_topic:{item_id}"),
        )
    ids = [d["item_id"] for d in storage.due_items(conn, TODAY)]
    assert ids == sorted(ids)


def test_due_items_limit_and_category(conn):
    _seed(conn)
    assert len(storage.due_items(conn, TODAY, limit=1)) == 1
    assert len(storage.due_items(conn, TODAY, category="測試")) == 2
    assert storage.due_items(conn, TODAY, category="不存在的分類") == []


def test_due_items_can_exclude_new_items(conn):
    _seed(conn)
    storage.add_item(conn, "by_topic:全新項目", today=TODAY)
    assert len(storage.due_items(conn, TODAY)) == 3
    assert len(storage.due_items(conn, TODAY, include_new=False)) == 2


def test_upcoming_excludes_today(conn):
    _seed(conn)
    upcoming = storage.upcoming_items(conn, TODAY, days=30)
    assert [u["title"] for u in upcoming] == ["滅火器設置"]
    assert storage.upcoming_items(conn, TODAY, days=5) == []


# --- 試算、重設、統計、輸出 ---------------------------------------------------


def test_preview_does_not_write(conn):
    storage.add_item(conn, ITEM["item_id"], today=TODAY)
    result = storage.preview_review(conn, ITEM["item_id"], 4, today=TODAY)
    assert result["after"]["next_review"] == "2026-07-31"
    assert storage.get_item(conn, ITEM["item_id"])["next_review"] is None
    assert storage.history(conn, ITEM["item_id"]) == []


def test_preview_works_without_any_db():
    result = storage.preview_review(None, "by_topic:閃燃", 5, today=TODAY)
    assert result["before"]["repetitions"] == 0
    assert result["after"]["interval_days"] == 1
    assert result["dry_run"] is True


def test_reset_item_keeps_metadata_and_history(conn):
    storage.record_review(conn, ITEM["item_id"], 4, today=TODAY, **_meta())
    item = storage.reset_item(conn, ITEM["item_id"])
    assert (item["repetitions"], item["interval_days"]) == (0, 0)
    assert item["next_review"] is None
    assert item["citation"] == ITEM["citation"]
    assert len(storage.history(conn, ITEM["item_id"])) == 1


def test_reset_unknown_item_errors(conn):
    with pytest.raises(StorageError):
        storage.reset_item(conn, "by_topic:沒這個")


def test_delete_unknown_item_returns_false(conn):
    assert storage.delete_item(conn, "by_topic:沒這個") is False


def test_stats_counts(conn):
    _seed(conn)
    storage.record_review(conn, "by_topic:閃燃", 4, today=TODAY)
    storage.record_review(conn, "by_topic:爆燃", 1, today=TODAY)
    data = storage.stats(conn, TODAY)
    assert data["total_items"] == 5
    assert data["due_today"] == 2  # 兩筆已到期；剛答完的兩筆排到明天
    assert data["overdue"] == 1
    assert data["reviews_logged"] == 2
    assert data["correct_rate"] == 0.5
    assert data["by_category"]["測試"] == 3
    assert data["weakest"][0]["ease_factor"] == 1.4


def test_stats_on_empty_db(conn):
    data = storage.stats(conn, TODAY)
    assert data["total_items"] == 0
    assert data["correct_rate"] is None


def test_json_record_matches_documented_shape(conn):
    storage.record_review(conn, ITEM["item_id"], 4, today=TODAY, q_id="自出題/2026-07-30#1", **_meta())
    record = storage.to_json_record(conn, ITEM["item_id"])
    assert set(record) == {
        "item_id", "title", "category", "citation", "ease_factor",
        "interval_days", "repetitions", "last_reviewed", "next_review", "history",
    }
    assert record == {
        "item_id": ITEM["item_id"],
        "title": ITEM["title"],
        "category": ITEM["category"],
        "citation": ITEM["citation"],
        "ease_factor": 2.5,
        "interval_days": 1,
        "repetitions": 0 + 1,
        "last_reviewed": TODAY,
        "next_review": "2026-07-31",
        "history": [
            {
                "date": TODAY,
                "result": "correct",
                "quality": 4,
                "interval_days": 1,
                "ease_factor": 2.5,
                "q_id": "自出題/2026-07-30#1",
            }
        ],
    }


def test_json_record_missing_item(conn):
    assert storage.to_json_record(conn, "by_topic:沒這個") is None


# --- 路徑解析 -----------------------------------------------------------------


def test_default_db_path_prefers_argument(monkeypatch):
    monkeypatch.setenv("FIRE_SAFETY_DATA_DIR", "/tmp/來自環境變數")
    assert storage.default_db_path("/tmp/來自參數") == \
        __import__("pathlib").Path("/tmp/來自參數") / storage.DB_FILENAME


def test_default_db_path_falls_back_to_env_then_default(monkeypatch):
    monkeypatch.setenv("FIRE_SAFETY_DATA_DIR", "/tmp/來自環境變數")
    assert str(storage.default_db_path()).startswith("/tmp/來自環境變數")
    monkeypatch.delenv("FIRE_SAFETY_DATA_DIR")
    path = storage.default_db_path()
    assert path.name == storage.DB_FILENAME
    assert ".fire-safety-tutor" in str(path)
    assert "~" not in str(path)  # 須展開為家目錄


def test_db_never_lands_in_plugin_dir(monkeypatch, tmp_path):
    """鐵則：排程檔只寫 data_dir，不寫 plugin 目錄。"""
    monkeypatch.delenv("FIRE_SAFETY_DATA_DIR", raising=False)
    plugin_root = __import__("pathlib").Path(storage.__file__).resolve().parents[2]
    assert plugin_root not in storage.default_db_path().parents


def test_foreign_keys_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO review_history (item_id, date, result, quality, "
            "interval_days, ease_factor) VALUES ('by_topic:孤兒', ?, 'correct', 4, 1, 2.5)",
            (TODAY,),
        )
