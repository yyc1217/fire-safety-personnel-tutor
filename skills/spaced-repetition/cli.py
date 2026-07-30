#!/usr/bin/env python3
"""間隔重複複習排程的指令介面（供 spaced-repetition skill 叫用）。

    python3 cli.py init
    python3 cli.py due --limit 5
    python3 cli.py record by_article:設置標準第82條 --quality 4
    python3 cli.py record by_equipment:滅火器 --essay 18/25
    python3 cli.py preview by_article:設置標準第82條 --quality 4   # 試算不寫檔
    python3 cli.py stats

排程檔位置預設 `~/.fire-safety-tutor/review_schedule.db`；`--data-dir`
或環境變數 `FIRE_SAFETY_DATA_DIR` 可改（一律在使用者 `data_dir` 之下，
不寫 plugin 目錄）。

## 為什麼不是互動式 REPL

`skills/spaced-repetition/SKILL.md` 才是「互動式複習介面」——出題、追問、
講解、判定品質分數都由 Claude 在對話中進行；本檔是它的**決定性後端**：
`due` 取出今天要複習什麼、`record` 把結果算進排程。Claude Code 的 Bash
工具沒有互動 stdin，寫成 `input()` 迴圈在此環境跑不起來，也會把「出題與
講解」這件真正需要模型的事塞進 shell。故本檔一律**單次執行、可預期輸出**
（加 `--json` 即機器可讀）。

所有輸出為繁體中文（與 plugin 其餘部分一致）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scheduler  # noqa: E402
import storage  # noqa: E402
from scheduler import SchedulerError  # noqa: E402
from storage import StorageError  # noqa: E402


# --- 輸出小工具 ---------------------------------------------------------------


def _out(text: str = "") -> None:
    print(text)


def _dump(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _day_phrase(target: str | None, today: date) -> str:
    """把日期換成「3 天前」「今天」「6 天後」這種人看得懂的說法。"""
    if not target:
        return "未排程"
    delta = (scheduler.parse_date(target) - today).days
    if delta == 0:
        return "今天"
    if delta < 0:
        return f"{-delta} 天前"
    return f"{delta} 天後"


_RESULT_LABEL = {"correct": "答對", "wrong": "答錯"}


def _format_due_line(index: int, item: dict[str, Any], today: date) -> str:
    title = item["title"] or item["item_id"]
    lines = [f"{index}. [ease {item['ease_factor']:.2f}] {title}"]
    if item["citation"]:
        lines.append(f"   依據：{item['citation']}")
    if item["last_reviewed"] and item["next_review"]:
        overdue = (today - scheduler.parse_date(item["next_review"])).days
        late = f"（逾期 {overdue} 天）" if overdue > 0 else ""
        last = _RESULT_LABEL.get(item.get("last_result") or "", "—")
        lines.append(
            f"   → 上次複習：{_day_phrase(item['last_reviewed'], today)}{late}"
            f"｜上次結果：{last}｜連續答對：{item['repetitions']} 次"
        )
    else:
        lines.append("   → 新項目，尚未複習過")
    lines.append(f"   item_id：{item['item_id']}")
    return "\n".join(lines)


def _format_record_result(item: dict[str, Any], quality: int, today: date) -> str:
    prev = item["previous"]
    result = "答對" if quality >= scheduler.PASSING_QUALITY else "答錯"
    head = f"✅ 已記錄：{item['title'] or item['item_id']}（quality {quality}／{result}）"
    detail = (
        f"   ease {prev['ease_factor']:.2f} → {item['ease_factor']:.2f}"
        f"｜間隔 {prev['interval_days']} → {item['interval_days']} 天"
        f"｜連續答對 {item['repetitions']} 次"
    )
    nxt = (
        f"   下次複習：{item['next_review']}"
        f"（{_day_phrase(item['next_review'], today)}）"
    )
    lines = [head, detail, nxt]
    if prev["is_new"]:
        lines.insert(1, "   （本項為新加入排程）")
    if quality < scheduler.PASSING_QUALITY:
        lines.append("   ⚠️ 答錯已重置：連續答對歸零、間隔回到 1 天，明天再考一次。")
    return "\n".join(lines)


# --- 各子指令 -----------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    path = storage.init_db(args.db)
    if args.json:
        _dump({"db": str(path), "schema_version": storage.SCHEMA_VERSION})
    else:
        _out(f"✅ 排程檔就緒：{path}（schema v{storage.SCHEMA_VERSION}）")
        _out("   排程只存「什麼時候該再看一次」；作答內容與掌握度仍在 progress.json。")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    with storage.connect(args.db, create=True) as conn:
        storage.migrate(conn)
        item = storage.add_item(
            conn,
            args.item_id,
            title=args.title,
            category=args.category,
            citation=args.citation,
            today=args.today,
        )
    _warn_unknown_prefix(args.item_id)
    if args.json:
        _dump(item)
    else:
        _out(f"✅ 已加入排程：{item['title'] or item['item_id']}")
        _out(f"   item_id：{item['item_id']}｜分類：{item['category'] or '（未分類）'}")
        if item["citation"]:
            _out(f"   依據：{item['citation']}")
        _out("   尚未複習過 → 立即列為到期，可在下一輪 due 取出。")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    quality = _resolve_quality(args)
    if args.dry_run:
        return _preview(args, quality)
    with storage.connect(args.db, create=True) as conn:
        storage.migrate(conn)
        item = storage.record_review(
            conn,
            args.item_id,
            quality,
            today=args.today,
            title=args.title,
            category=args.category,
            citation=args.citation,
            q_id=args.q_id,
            note=args.note,
        )
    _warn_unknown_prefix(args.item_id)
    if args.json:
        _dump(item)
    else:
        _out(_format_record_result(item, quality, scheduler.parse_date(args.today)))
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    return _preview(args, _resolve_quality(args))


def _preview(args: argparse.Namespace, quality: int) -> int:
    db = Path(args.db).expanduser()
    if db.exists():
        with storage.connect(db) as conn:
            storage.migrate(conn)
            result = storage.preview_review(
                conn, args.item_id, quality, today=args.today
            )
    else:
        result = storage.preview_review(None, args.item_id, quality, today=args.today)
    if args.json:
        _dump(result)
    else:
        before, after = result["before"], result["after"]
        _out(f"🔍 試算（**不寫檔**）：{result['item_id']}，quality {quality}")
        _out(
            f"   ease {before['ease_factor']:.2f} → {after['ease_factor']:.2f}"
            f"｜間隔 {before['interval_days']} → {after['interval_days']} 天"
            f"｜連續答對 {before['repetitions']} → {after['repetitions']} 次"
        )
        _out(
            f"   若此刻記錄，下次複習會排在 {after['next_review']}"
            f"（{_day_phrase(after['next_review'], scheduler.parse_date(args.today))}）"
        )
    return 0


def cmd_due(args: argparse.Namespace) -> int:
    today = scheduler.parse_date(args.today)
    with storage.connect(args.db) as conn:
        storage.migrate(conn)
        items = storage.due_items(
            conn,
            today,
            limit=args.limit,
            category=args.category,
            include_new=not args.no_new,
        )
        total = len(storage.all_items(conn))
        upcoming = storage.upcoming_items(conn, today, days=30)
    if args.json:
        _dump({"as_of": today.isoformat(), "total_items": total, "due": items})
        return 0
    if not items:
        _out(f"✅ 今天（{today.isoformat()}）沒有到期的複習項目。")
        if upcoming:
            nxt = upcoming[0]
            _out(
                f"   排程中共 {total} 項，下一項 {nxt['next_review']} 到期"
                f"（{_day_phrase(nxt['next_review'], today)}）："
                f"{nxt['title'] or nxt['item_id']}"
            )
        elif total:
            _out(f"   排程中共 {total} 項，均已排到 30 天後。")
        else:
            _out("   排程還是空的——先做幾輪 /抽考 或 /弱點複習，批改後會自動建立項目。")
        return 0
    scope = f"，範圍：{args.category}" if args.category else ""
    _out(f"📋 今日待複習（{len(items)} 項，依弱點排序{scope}）：")
    _out()
    for i, item in enumerate(items, 1):
        _out(_format_due_line(i, item, today))
        _out()
    _out(f"（排程共 {total} 項；ease 越低代表記得越不牢，故排在前面）")
    return 0


def cmd_upcoming(args: argparse.Namespace) -> int:
    today = scheduler.parse_date(args.today)
    with storage.connect(args.db) as conn:
        storage.migrate(conn)
        items = storage.upcoming_items(conn, today, days=args.days)
    if args.json:
        _dump({"as_of": today.isoformat(), "days": args.days, "upcoming": items})
        return 0
    if not items:
        _out(f"（未來 {args.days} 天內沒有排定的複習項目）")
        return 0
    _out(f"🗓️ 未來 {args.days} 天的複習排程：")
    for item in items:
        _out(
            f"  {item['next_review']}（{_day_phrase(item['next_review'], today)}）"
            f" [ease {item['ease_factor']:.2f}] {item['title'] or item['item_id']}"
        )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    with storage.connect(args.db) as conn:
        storage.migrate(conn)
        record = storage.to_json_record(conn, args.item_id)
    if record is None:
        _out(f"（排程中沒有這個項目：{args.item_id}）")
        return 1
    if args.json:
        _dump(record)
        return 0
    today = scheduler.parse_date(args.today)
    _out(f"📌 {record['title'] or record['item_id']}")
    _out(f"   item_id：{record['item_id']}")
    _out(f"   分類：{record['category'] or '（未分類）'}")
    _out(f"   依據：{record['citation'] or '（未填）'}")
    _out(
        f"   ease {record['ease_factor']:.2f}｜間隔 {record['interval_days']} 天"
        f"｜連續答對 {record['repetitions']} 次"
    )
    _out(
        f"   上次複習：{record['last_reviewed'] or '（無）'}"
        f"｜下次複習：{record['next_review'] or '（未排程）'}"
        f"（{_day_phrase(record['next_review'], today)}）"
    )
    if record["history"]:
        _out("   複習歷程：")
        for h in record["history"]:
            tail = f"｜{h['q_id']}" if h.get("q_id") else ""
            _out(
                f"     {h['date']} {_RESULT_LABEL.get(h['result'], h['result'])}"
                f"（quality {h['quality']}）→ 間隔 {h['interval_days']} 天"
                f"、ease {h['ease_factor']:.2f}{tail}"
            )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with storage.connect(args.db) as conn:
        storage.migrate(conn)
        items = storage.all_items(conn, category=args.category)
    if args.json:
        _dump(items)
        return 0
    if not items:
        _out("（排程是空的）")
        return 0
    today = scheduler.parse_date(args.today)
    _out(f"排程共 {len(items)} 項（依 ease 由低到高）：")
    for item in items:
        _out(
            f"  [ease {item['ease_factor']:.2f}] {item['title'] or item['item_id']}"
            f"｜下次 {item['next_review'] or '未排程'}"
            f"（{_day_phrase(item['next_review'], today)}）"
        )
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    today = scheduler.parse_date(args.today)
    with storage.connect(args.db) as conn:
        storage.migrate(conn)
        data = storage.stats(conn, today)
    if args.json:
        _dump(data)
        return 0
    _out(f"📊 複習排程統計（{data['as_of']}）")
    _out(f"   總項目：{data['total_items']}｜今日到期：{data['due_today']}｜逾期：{data['overdue']}")
    if data["correct_rate"] is not None:
        _out(
            f"   累計複習 {data['reviews_logged']} 次，答對率 "
            f"{data['correct_rate'] * 100:.0f}%"
        )
    if data["by_category"]:
        _out("   分類分布：" + "、".join(f"{k} {v}" for k, v in data["by_category"].items()))
    if data["weakest"]:
        _out("   最弱五項：")
        for item in data["weakest"]:
            _out(
                f"     [ease {item['ease_factor']:.2f}] {item['title'] or item['item_id']}"
                f"｜{item['citation'] or '（無依據）'}"
            )
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    with storage.connect(args.db) as conn:
        storage.migrate(conn)
        item = storage.reset_item(conn, args.item_id, keep_history=not args.purge_history)
    _out(f"↩️ 已打回未學狀態：{item['title'] or item['item_id']}（ease 2.5、間隔 0）")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    with storage.connect(args.db) as conn:
        storage.migrate(conn)
        removed = storage.delete_item(conn, args.item_id)
    if removed:
        _out(f"🗑️ 已從排程移除：{args.item_id}（含其複習歷程）")
        return 0
    _out(f"（排程中沒有這個項目：{args.item_id}）")
    return 1


def cmd_import(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.file).expanduser().read_text(encoding="utf-8"))
    items = raw["items"] if isinstance(raw, dict) else raw
    with storage.connect(args.db, create=True) as conn:
        storage.migrate(conn)
        count = storage.import_items(conn, items, today=args.today)
    _out(f"✅ 已匯入／更新 {count} 項（只建描述，不動既有排程）。")
    return 0


# --- 品質分數解析 -------------------------------------------------------------


def _resolve_quality(args: argparse.Namespace) -> int:
    """由 `--quality`／`--essay`／`--result` 三種給法取得 0–5 品質分數。

    對映規則的唯一真相是 `scheduler.quality_from_*`，本函式只做參數轉換。
    """
    given = [args.quality is not None, args.essay is not None, args.result is not None]
    if sum(given) != 1:
        raise SchedulerError(
            "請剛好給一種評分方式：--quality 0-5、--essay 得分/滿分、"
            "或 --result correct|wrong（可搭配 --hinted／--unsure／--partial／--blank）"
        )
    if args.quality is not None:
        return scheduler.validate_quality(args.quality)
    if args.essay is not None:
        score, _, max_score = str(args.essay).partition("/")
        if not max_score:
            max_score = "25"  # 申論每題預設 25 分（見 exam-tutor 批改配分）
        try:
            return scheduler.quality_from_essay(float(score), float(max_score))
        except ValueError as exc:
            raise SchedulerError(f"--essay 格式須為 得分/滿分（如 18/25）：{args.essay!r}") from exc
    return scheduler.quality_from_choice(
        args.result == "correct",
        hinted=args.hinted,
        unsure=args.unsure,
        partial=args.partial,
        blank=args.blank,
    )


def _warn_unknown_prefix(item_id: str) -> None:
    """item_id 前綴不在既有標籤維度內時提醒（不阻擋）。"""
    if not storage.has_known_prefix(item_id):
        print(
            f"⚠️ item_id「{storage.base_tag(item_id)}」不是既有標籤維度前綴"
            f"（{'、'.join(storage.KNOWN_ITEM_PREFIXES)}）。"
            "已照樣存入，但這樣就無法用 jq 對 corpus/tags_index.json 反查考古題，"
            "請確認命名（規格見 reference/複習排程規格.md）。",
            file=sys.stderr,
        )


# --- 參數 ---------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="消防設備師／士備考：間隔重複複習排程（SM-2 簡化版）",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="學習資料目錄（預設取環境變數 FIRE_SAFETY_DATA_DIR，再退回 ~/.fire-safety-tutor）",
    )
    parser.add_argument(
        "--db", default=None, help="直接指定排程檔路徑（優先於 --data-dir）"
    )
    parser.add_argument("--today", default=None, help="以指定日期為「今天」（YYYY-MM-DD，測試與補記用）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON（機器可讀）")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="建立或升級排程檔（冪等）").set_defaults(func=cmd_init)

    def add_meta(p: argparse.ArgumentParser) -> None:
        p.add_argument("item_id", help="知識點 ID：tag key，或 tag key#要點名")
        p.add_argument("--title", default="", help="人看的名稱（如「CO₂ 藥劑保持時間計算」）")
        p.add_argument("--category", default="", help="分類（科目或系統，如「化學系統」）")
        p.add_argument("--citation", default="", help="法規依據（如「設置標準 §82」）")

    p_add = sub.add_parser("add", help="加入項目（只建描述、不排程）")
    add_meta(p_add)
    p_add.set_defaults(func=cmd_add)

    p_record = sub.add_parser("record", help="記錄一次作答結果並更新排程")
    add_meta(p_record)
    _add_quality_args(p_record)
    p_record.add_argument("--q-id", default=None, help="對應 progress.json 之 attempts.q_id")
    p_record.add_argument("--note", default=None, help="備註（如錯在哪）")
    p_record.add_argument("--dry-run", action="store_true", help="只試算、不寫檔")
    p_record.set_defaults(func=cmd_record)

    p_preview = sub.add_parser("preview", help="試算某品質分數的結果（絕不寫檔）")
    p_preview.add_argument("item_id")
    _add_quality_args(p_preview)
    p_preview.set_defaults(func=cmd_preview)

    p_due = sub.add_parser("due", help="列出今日（含逾期）到期項目，依 ease 由低到高")
    p_due.add_argument("--limit", type=int, default=None, help="最多幾項")
    p_due.add_argument("--category", default=None, help="只看某分類")
    p_due.add_argument("--no-new", action="store_true", help="排除從未複習過的新項目")
    p_due.set_defaults(func=cmd_due)

    p_up = sub.add_parser("upcoming", help="未來幾天的排程預覽")
    p_up.add_argument("--days", type=int, default=7)
    p_up.set_defaults(func=cmd_upcoming)

    p_show = sub.add_parser("show", help="看單一項目（含複習歷程）")
    p_show.add_argument("item_id")
    p_show.set_defaults(func=cmd_show)

    p_list = sub.add_parser("list", help="列出全部項目")
    p_list.add_argument("--category", default=None)
    p_list.set_defaults(func=cmd_list)

    sub.add_parser("stats", help="總覽統計").set_defaults(func=cmd_stats)

    p_reset = sub.add_parser("reset", help="把項目打回未學狀態")
    p_reset.add_argument("item_id")
    p_reset.add_argument("--purge-history", action="store_true", help="同時刪掉複習歷程")
    p_reset.set_defaults(func=cmd_reset)

    p_rm = sub.add_parser("remove", help="從排程移除項目")
    p_rm.add_argument("item_id")
    p_rm.set_defaults(func=cmd_remove)

    p_imp = sub.add_parser("import", help="由 JSON 批次加入項目")
    p_imp.add_argument("file", help="JSON 檔（items 陣列，或直接是陣列）")
    p_imp.set_defaults(func=cmd_import)

    return parser


def _add_quality_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("評分（三種給法擇一）")
    g.add_argument("--quality", type=int, default=None, help="直接給 0–5")
    g.add_argument("--essay", default=None, help="申論得分，如 18/25（預設滿分 25）")
    g.add_argument("--result", choices=["correct", "wrong"], default=None, help="選擇題結果")
    g.add_argument("--hinted", action="store_true", help="搭配 --result：經提示才答對 → 3")
    g.add_argument("--unsure", action="store_true", help="搭配 --result：答對但自陳不確定 → 4")
    g.add_argument("--partial", action="store_true", help="搭配 --result：答錯但方向對 → 2")
    g.add_argument("--blank", action="store_true", help="搭配 --result：未作答／完全不會 → 0")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.today = args.today or date.today().isoformat()
    if args.db is None:
        args.db = str(storage.default_db_path(args.data_dir))
    try:
        scheduler.parse_date(args.today)
        return int(args.func(args))
    except (SchedulerError, StorageError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"❌ JSON 無法解析：{exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"❌ 找不到檔案：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
