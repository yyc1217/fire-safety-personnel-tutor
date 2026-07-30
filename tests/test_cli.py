"""`skills/spaced-repetition/cli.py` 的介面測試。

以 `cli.main()` 直接呼叫（不另起 process），並以 capsys 檢查輸出——
skill 是靠讀這些文字與 JSON 行事的，格式即介面契約。
"""

from __future__ import annotations

import json

import pytest

import cli

TODAY = "2026-07-30"


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "review_schedule.db")


def run(db, *argv, expect=0):
    code = cli.main(["--db", db, "--today", TODAY, *argv])
    assert code == expect, f"預期結束碼 {expect}，實得 {code}：{argv}"
    return code


def run_json(db, *argv, capsys=None, expect=0):
    run(db, "--json", *argv, expect=expect)
    return json.loads(capsys.readouterr().out)


# --- init ---------------------------------------------------------------------


def test_init_creates_db(db, capsys):
    run(db, "init")
    assert "排程檔就緒" in capsys.readouterr().out
    run(db, "init")  # 冪等


def test_due_before_init_explains_itself(db, capsys):
    run(db, "due", expect=2)
    assert "找不到排程檔" in capsys.readouterr().err


# --- add / record -------------------------------------------------------------


def test_add_then_due_lists_new_item(db, capsys):
    run(db, "init")
    run(
        db, "add", "by_article:設置標準第82條#藥劑保持時間",
        "--title", "CO₂ 藥劑保持時間計算",
        "--category", "化學系統",
        "--citation", "各類場所消防安全設備設置標準 §82",
    )
    capsys.readouterr()
    run(db, "due")
    out = capsys.readouterr().out
    assert "今日待複習（1 項" in out
    assert "CO₂ 藥劑保持時間計算" in out
    assert "依據：各類場所消防安全設備設置標準 §82" in out
    assert "新項目，尚未複習過" in out


def test_record_creates_item_and_reports_change(db, capsys):
    run(db, "record", "by_topic:閃燃", "--quality", "4", "--title", "閃燃條件")
    out = capsys.readouterr().out
    assert "已記錄：閃燃條件（quality 4／答對）" in out
    assert "本項為新加入排程" in out
    assert "下次複習：2026-07-31（1 天後）" in out


def test_record_wrong_answer_warns_about_reset(db, capsys):
    run(db, "record", "by_topic:閃燃", "--quality", "4")
    run(db, "record", "by_topic:閃燃", "--quality", "1")
    out = capsys.readouterr().out
    assert "答錯已重置" in out


def test_record_essay_score_maps_to_quality(db, capsys):
    data = run_json(db, "record", "by_equipment:滅火器", "--essay", "18/25", capsys=capsys)
    assert data["repetitions"] == 1  # 18/25 = 0.72 → quality 3（答對）
    assert data["ease_factor"] == 2.36


def test_record_essay_defaults_to_25_point_scale(db, capsys):
    data = run_json(db, "record", "by_equipment:滅火器", "--essay", "24", capsys=capsys)
    assert data["ease_factor"] == 2.6  # 24/25 → quality 5


def test_record_choice_result_flags(db, capsys):
    data = run_json(db, "record", "by_topic:熱傳", "--result", "correct", capsys=capsys)
    assert data["ease_factor"] == 2.6  # quality 5
    data = run_json(
        db, "record", "by_topic:靜電", "--result", "wrong", "--partial", capsys=capsys
    )
    assert data["repetitions"] == 0
    assert data["ease_factor"] == 2.18  # quality 2


def test_record_requires_exactly_one_scoring_method(db, capsys):
    run(db, "record", "by_topic:熱傳", expect=2)
    assert "請剛好給一種評分方式" in capsys.readouterr().err
    run(db, "record", "by_topic:熱傳", "--quality", "4", "--essay", "20/25", expect=2)
    assert "請剛好給一種評分方式" in capsys.readouterr().err


def test_record_rejects_out_of_range_quality(db, capsys):
    run(db, "record", "by_topic:熱傳", "--quality", "7", expect=2)
    assert "0–5" in capsys.readouterr().err


def test_record_dry_run_writes_nothing(db, capsys):
    run(db, "init")
    run(db, "record", "by_topic:爆炸", "--quality", "5", "--dry-run")
    assert "不寫檔" in capsys.readouterr().out
    run(db, "list")
    assert "排程是空的" in capsys.readouterr().out


def test_unknown_item_id_prefix_warns_but_records(db, capsys):
    run(db, "record", "co2_hold_time_calc", "--quality", "4")
    captured = capsys.readouterr()
    assert "不是既有標籤維度前綴" in captured.err
    assert "已記錄" in captured.out


# --- due / upcoming / show / list / stats ------------------------------------


def _seed_three(db):
    run(db, "init")
    run(db, "record", "by_article:設置標準第82條", "--quality", "0",
        "--title", "CO₂ 保持時間", "--category", "化學系統",
        "--citation", "設置標準 §82")
    run(db, "record", "by_article:設置標準第126條", "--quality", "3",
        "--title", "P 型受信總機分區上限", "--category", "警報系統",
        "--citation", "設置標準 §126")
    run(db, "record", "by_equipment:滅火器", "--quality", "5",
        "--title", "滅火器設置", "--category", "化學系統")


def test_due_sorted_weakest_first(db, capsys):
    _seed_three(db)
    capsys.readouterr()
    # 三項都排在 07-31：以 07-31 為今天來看到期清單
    cli.main(["--db", db, "--today", "2026-07-31", "due"])
    out = capsys.readouterr().out
    order = [line for line in out.splitlines() if line and line[0].isdigit()]
    assert "CO₂ 保持時間" in order[0]  # ease 1.7 最低
    assert "P 型受信總機分區上限" in order[1]  # ease 2.36
    assert "滅火器設置" in order[2]  # ease 2.6
    assert "逾期" not in out


def test_due_reports_overdue_days(db, capsys):
    _seed_three(db)
    capsys.readouterr()
    cli.main(["--db", db, "--today", "2026-08-03", "due", "--limit", "1"])
    out = capsys.readouterr().out
    assert "（逾期 3 天）" in out
    assert "上次複習：4 天前" in out
    assert "上次結果：答錯" in out  # 看得出為什麼這項排最前面


def test_due_empty_points_at_next_item(db, capsys):
    _seed_three(db)
    capsys.readouterr()
    run(db, "due")  # 07-30 當天全部已排到 07-31
    out = capsys.readouterr().out
    assert "沒有到期的複習項目" in out
    assert "下一項 2026-07-31 到期" in out


def test_due_on_empty_schedule_suggests_practising(db, capsys):
    run(db, "init")
    capsys.readouterr()
    run(db, "due")
    assert "/抽考" in capsys.readouterr().out


def test_due_json_shape(db, capsys):
    _seed_three(db)
    capsys.readouterr()
    cli.main(["--db", db, "--today", "2026-07-31", "--json", "due", "--limit", "2"])
    data = json.loads(capsys.readouterr().out)
    assert data["as_of"] == "2026-07-31"
    assert data["total_items"] == 3
    assert len(data["due"]) == 2
    assert data["due"][0]["item_id"] == "by_article:設置標準第82條"
    assert data["due"][0]["citation"] == "設置標準 §82"


def test_due_category_filter(db, capsys):
    _seed_three(db)
    capsys.readouterr()
    cli.main(["--db", db, "--today", "2026-07-31", "--json", "due", "--category", "警報系統"])
    data = json.loads(capsys.readouterr().out)
    assert [d["title"] for d in data["due"]] == ["P 型受信總機分區上限"]


def test_upcoming(db, capsys):
    _seed_three(db)
    capsys.readouterr()
    run(db, "upcoming", "--days", "7")
    out = capsys.readouterr().out
    assert "未來 7 天的複習排程" in out
    assert out.count("2026-07-31") == 3


def test_show_includes_history_and_citation(db, capsys):
    _seed_three(db)
    capsys.readouterr()
    run(db, "show", "by_article:設置標準第82條")
    out = capsys.readouterr().out
    assert "依據：設置標準 §82" in out
    assert "複習歷程" in out
    assert "答錯（quality 0）" in out


def test_show_unknown_item_exits_nonzero(db, capsys):
    run(db, "init")
    run(db, "show", "by_topic:沒這個", expect=1)


def test_stats_summary(db, capsys):
    _seed_three(db)
    capsys.readouterr()
    run(db, "stats")
    out = capsys.readouterr().out
    assert "總項目：3" in out
    assert "答對率 67%" in out
    assert "最弱五項" in out


# --- preview / reset / remove / import ---------------------------------------


def test_preview_without_db_still_works(db, capsys):
    run(db, "preview", "by_topic:閃燃", "--quality", "4")
    out = capsys.readouterr().out
    assert "不寫檔" in out
    assert "2026-07-31" in out


def test_preview_uses_existing_state(db, capsys):
    run(db, "record", "by_topic:閃燃", "--quality", "4")
    capsys.readouterr()
    data = run_json(db, "preview", "by_topic:閃燃", "--quality", "4", capsys=capsys)
    assert data["before"]["repetitions"] == 1
    assert data["after"]["interval_days"] == 6
    assert data["dry_run"] is True


def test_reset_and_remove(db, capsys):
    run(db, "record", "by_topic:閃燃", "--quality", "4")
    capsys.readouterr()
    run(db, "reset", "by_topic:閃燃")
    assert "打回未學狀態" in capsys.readouterr().out
    run(db, "remove", "by_topic:閃燃")
    assert "已從排程移除" in capsys.readouterr().out
    run(db, "remove", "by_topic:閃燃", expect=1)


def test_import_items(db, tmp_path, capsys):
    payload = tmp_path / "items.json"
    payload.write_text(
        json.dumps(
            {
                "items": [
                    {"item_id": "by_topic:爆燃", "title": "爆燃", "category": "火災學"},
                    {"item_id": "by_topic:閃燃", "title": "閃燃", "category": "火災學"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    run(db, "import", str(payload))
    assert "已匯入／更新 2 項" in capsys.readouterr().out
    data = run_json(db, "due", capsys=capsys)
    assert len(data["due"]) == 2


def test_import_bad_json(db, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{ 不是 JSON", encoding="utf-8")
    run(db, "import", str(bad), expect=2)
    assert "JSON 無法解析" in capsys.readouterr().err


def test_missing_import_file(db, capsys):
    run(db, "import", "/tmp/一定不存在的檔.json", expect=2)
    assert "找不到檔案" in capsys.readouterr().err


# --- 全域參數 -----------------------------------------------------------------


def test_data_dir_option_locates_db(tmp_path, capsys):
    assert cli.main(["--data-dir", str(tmp_path), "init"]) == 0
    assert (tmp_path / "review_schedule.db").exists()
    assert str(tmp_path) in capsys.readouterr().out


def test_env_var_locates_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FIRE_SAFETY_DATA_DIR", str(tmp_path))
    assert cli.main(["init"]) == 0
    assert (tmp_path / "review_schedule.db").exists()


def test_bad_today_rejected(db, capsys):
    assert cli.main(["--db", db, "--today", "115-06-05", "due"]) == 2
    assert "西元 ISO" in capsys.readouterr().err
