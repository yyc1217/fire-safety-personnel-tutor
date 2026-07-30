#!/usr/bin/env python3
"""間隔重複複習排程核心演算法（SM-2 簡化版）。

本檔**純演算法、零 I/O**：不碰檔案、不碰 SQLite、不看環境變數，
只做「舊狀態 ＋ 本次品質分數 → 新狀態」的計算，故可完整單元測試
（見 `tests/test_scheduler.py`）。儲存層見 `storage.py`、介面見 `cli.py`。

## 為什麼要用程式算，不讓模型心算

1. **決定性**：`interval × ease_factor` 的乘算與日期加減，模型會算錯或每次略有不同；
   排程一旦漂移，「該複習了」就失去意義。
2. **精準取用**：到期項目用 SQL `WHERE next_review <= ?` 取，只把當天用得到的
   幾列讀進脈絡，不整檔載入（與 exam-tutor「索引與大檔取用原則」同一原則）。

## 演算法（規格唯一真相為 reference/複習排程規格.md，本檔為其實作）

答題後給 0–5 品質分數（0＝完全不會，5＝秒答對）：

- `quality < 3`（答錯）→ `repetitions = 0`、`interval_days = 1`
- `quality >= 3`（答對）→ `repetitions += 1`，並依連續答對次數定間隔：
  第 1 次 1 天、第 2 次 6 天、第 3 次以後 `round(前次 interval_days × ease_factor)`

`ease_factor` 每次答題後更新（含答錯），下限鎖 1.3：

    ease_factor += 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)

**兩個實作決定（原始 SM-2 描述留有空間，此處固定下來以免行為漂移）**：

1. **算間隔用「本次答題前」的 ease_factor**，算完才更新 ease_factor
   （即上式的「每次答題後」按字面實施）。Anki 等實作改用更新後的值，
   本檔不採；差異只在第 3 次以後的間隔，但必須固定一種才可測。
2. **四捨五入採 half-up**（`floor(x + 0.5)`），不用 Python 內建 `round()`
   的 banker's rounding——`round(2.5)` 得 2 而非 3，會讓間隔莫名少一天。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, timedelta

# --- 常數（與 reference/複習排程規格.md 一致） ---------------------------------

#: 新項目的初始 ease factor
DEFAULT_EASE_FACTOR = 2.5
#: ease factor 下限：再低會讓間隔近乎不成長、複習頻率失控
MIN_EASE_FACTOR = 1.3
#: 第 1 次答對的間隔（天）
FIRST_INTERVAL_DAYS = 1
#: 第 2 次答對的間隔（天）
SECOND_INTERVAL_DAYS = 6
#: 答錯後重置的間隔（天）
LAPSE_INTERVAL_DAYS = 1
#: 及格門檻：quality >= 此值視為答對
PASSING_QUALITY = 3
#: ease factor 存檔前的小數位數（避免浮點尾差累積成 2.3600000000000003）
EASE_PRECISION = 3


class SchedulerError(ValueError):
    """輸入不合演算法前提（品質分數越界、間隔為負等）。"""


@dataclass(frozen=True)
class ItemState:
    """單一知識點的排程狀態。

    對應 `review_items` 表的排程欄位；`category`／`citation` 等描述性欄位
    不影響計算，故不放進本結構（見 storage.py）。
    """

    ease_factor: float = DEFAULT_EASE_FACTOR
    interval_days: int = 0
    repetitions: int = 0
    last_reviewed: str | None = None
    next_review: str | None = None

    def __post_init__(self) -> None:
        if self.interval_days < 0:
            raise SchedulerError(f"interval_days 不得為負：{self.interval_days}")
        if self.repetitions < 0:
            raise SchedulerError(f"repetitions 不得為負：{self.repetitions}")
        if self.ease_factor < MIN_EASE_FACTOR:
            raise SchedulerError(
                f"ease_factor {self.ease_factor} 低於下限 {MIN_EASE_FACTOR}"
            )


# --- 純函式 -------------------------------------------------------------------


def _round_half_up(value: float) -> int:
    """四捨五入（half-up）。見檔首「實作決定 2」。"""
    return int(math.floor(value + 0.5))


def validate_quality(quality: int) -> int:
    """品質分數須為 0–5 的整數。"""
    if isinstance(quality, bool) or not isinstance(quality, int):
        raise SchedulerError(f"quality 須為整數 0–5：{quality!r}")
    if not 0 <= quality <= 5:
        raise SchedulerError(f"quality 須在 0–5 之間：{quality}")
    return quality


def update_ease_factor(ease_factor: float, quality: int) -> float:
    """回傳更新後的 ease factor（下限鎖 `MIN_EASE_FACTOR`）。"""
    validate_quality(quality)
    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    return round(max(MIN_EASE_FACTOR, ease_factor + delta), EASE_PRECISION)


def next_interval_days(
    interval_days: int, repetitions: int, quality: int, ease_factor: float
) -> int:
    """回傳下次間隔天數。

    `repetitions` 是**本次答題前**的連續答對次數；`ease_factor` 亦為答題前的值
    （見檔首「實作決定 1」）。
    """
    validate_quality(quality)
    if quality < PASSING_QUALITY:
        return LAPSE_INTERVAL_DAYS
    successes = repetitions + 1
    if successes == 1:
        return FIRST_INTERVAL_DAYS
    if successes == 2:
        return SECOND_INTERVAL_DAYS
    # 第 3 次以後：前次間隔 × ease factor。前次間隔異常（0／缺值）時至少推一天，
    # 避免 next_review 卡在今天而永遠到期。
    base = max(interval_days, FIRST_INTERVAL_DAYS)
    return max(FIRST_INTERVAL_DAYS, _round_half_up(base * ease_factor))


def review(state: ItemState, quality: int, today: date | str) -> ItemState:
    """套用一次複習結果，回傳新的排程狀態（不修改傳入的 state）。"""
    validate_quality(quality)
    today_date = parse_date(today)

    interval = next_interval_days(
        state.interval_days, state.repetitions, quality, state.ease_factor
    )
    repetitions = 0 if quality < PASSING_QUALITY else state.repetitions + 1
    return replace(
        state,
        ease_factor=update_ease_factor(state.ease_factor, quality),
        interval_days=interval,
        repetitions=repetitions,
        last_reviewed=today_date.isoformat(),
        next_review=(today_date + timedelta(days=interval)).isoformat(),
    )


def is_due(state: ItemState, today: date | str) -> bool:
    """尚未排程（`next_review` 為空）的新項目視為到期。"""
    if not state.next_review:
        return True
    return parse_date(state.next_review) <= parse_date(today)


# --- 日期工具 -----------------------------------------------------------------


def parse_date(value: date | str) -> date:
    """接受 `date` 或 ISO 字串（`YYYY-MM-DD`），一律回傳 `date`。

    民國年不在此處理：一切存檔日期皆為西元 ISO（見 user-config-spec.md）。
    """
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise SchedulerError(f"日期須為西元 ISO 格式 YYYY-MM-DD：{value!r}") from exc


# --- 批改結果 → 品質分數（對映表唯一真相：reference/複習排程規格.md） ----------

#: 申論題：得分率 → 品質分數。門檻由高至低比對，第一個符合者勝出。
#: 0.6（15／25）即實務及格線，故對到剛好及格的 quality 3。
ESSAY_QUALITY_THRESHOLDS = (
    (0.9, 5),
    (0.75, 4),
    (0.6, 3),
    (0.4, 2),
    (0.2, 1),
)


def quality_from_essay(score: float, max_score: float) -> int:
    """申論題得分（0–25 分制）換算品質分數。"""
    if max_score <= 0:
        raise SchedulerError(f"max_score 須為正數：{max_score}")
    if score < 0 or score > max_score:
        raise SchedulerError(f"score {score} 超出 0–{max_score} 範圍")
    ratio = score / max_score
    for threshold, quality in ESSAY_QUALITY_THRESHOLDS:
        if ratio >= threshold:
            return quality
    return 0


def quality_from_choice(
    correct: bool,
    *,
    hinted: bool = False,
    unsure: bool = False,
    partial: bool = False,
    blank: bool = False,
) -> int:
    """選擇題／簡答換算品質分數。

    - 答對且未經提示、答得果斷 → 5
    - 答對但自陳不確定或明說是猜的（`unsure`）→ 4
    - 經提示後才答對（`hinted`）→ 3
    - 答錯但方向對（`partial`：近似答案、單位或數值小錯）→ 2
    - 答錯 → 1
    - 未作答／完全不會（`blank`）→ 0
    """
    if blank:
        return 0
    if correct:
        if hinted:
            return PASSING_QUALITY
        return 4 if unsure else 5
    return 2 if partial else 1
