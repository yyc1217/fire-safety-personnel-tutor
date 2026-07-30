"""`skills/spaced-repetition/scheduler.py` 的單元測試（純演算法，不碰檔案）。

    python3 -m pytest tests/ -q
"""

from __future__ import annotations

from datetime import date

import pytest

import scheduler as sc
from scheduler import ItemState, SchedulerError, review

TODAY = date(2026, 7, 30)


def answer_series(qualities, *, start=TODAY, state=None):
    """連續答題，回傳每一次答完後的狀態清單。"""
    current = state or ItemState()
    out = []
    day = start
    for quality in qualities:
        current = review(current, quality, day)
        out.append(current)
        day = sc.parse_date(current.next_review)
    return out


# --- 連續答對：間隔 1 → 6 → 前次 × ease_factor ---------------------------------


def test_first_correct_gives_one_day():
    state = review(ItemState(), 4, TODAY)
    assert state.repetitions == 1
    assert state.interval_days == 1
    assert state.last_reviewed == "2026-07-30"
    assert state.next_review == "2026-07-31"


def test_second_correct_gives_six_days():
    first, second = answer_series([4, 4])
    assert first.interval_days == 1
    assert second.repetitions == 2
    assert second.interval_days == 6
    # 隔天複習（07-31）＋6 天
    assert second.last_reviewed == "2026-07-31"
    assert second.next_review == "2026-08-06"


def test_third_correct_multiplies_previous_interval_by_ease():
    """quality 4 不動 ease（±0），故第 3 次為 round(6 × 2.5) = 15。"""
    states = answer_series([4, 4, 4])
    assert [s.ease_factor for s in states] == [2.5, 2.5, 2.5]
    assert [s.interval_days for s in states] == [1, 6, 15]
    assert states[-1].repetitions == 3
    assert states[-1].next_review == "2026-08-21"  # 08-06 ＋15 天


def test_fourth_correct_compounds_on_the_new_interval():
    states = answer_series([4, 4, 4, 4])
    # 15 × 2.5 = 37.5 → half-up → 38
    assert states[-1].interval_days == 38
    assert states[-1].repetitions == 4


def test_interval_uses_pre_update_ease_factor():
    """算間隔用「答題前」的 ease，算完才更新（scheduler 檔首實作決定 1）。"""
    states = answer_series([5, 5, 5])
    # 兩次 quality 5 各 +0.1 → 第 3 次答題時的 ease 仍是 2.7，非更新後的 2.8
    assert [s.ease_factor for s in states] == [2.6, 2.7, 2.8]
    assert states[-1].interval_days == sc._round_half_up(6 * 2.7) == 16


def test_rounding_is_half_up_not_bankers():
    """round(2.5) 在 Python 是 2（banker's）；本演算法要 3。"""
    assert sc._round_half_up(2.5) == 3
    assert sc._round_half_up(37.5) == 38
    assert sc._round_half_up(3.4) == 3
    # 前次間隔 5、ease 1.3 → 6.5 → 7（若用內建 round 會得 6）
    state = ItemState(ease_factor=1.3, interval_days=5, repetitions=2)
    assert review(state, 4, TODAY).interval_days == 7


# --- 答錯：repetitions 歸零、interval 重置 -------------------------------------


@pytest.mark.parametrize("quality", [0, 1, 2])
def test_wrong_answer_resets_repetitions_and_interval(quality):
    grown = answer_series([4, 4, 4])[-1]
    assert (grown.repetitions, grown.interval_days) == (3, 15)

    lapsed = review(grown, quality, date(2026, 8, 21))
    assert lapsed.repetitions == 0
    assert lapsed.interval_days == 1
    assert lapsed.next_review == "2026-08-22"


def test_relearning_after_lapse_restarts_the_ladder():
    """答錯歸零後，重新答對是從 1 天再走，不是接回原本的長間隔。"""
    states = answer_series([4, 4, 4, 1, 4, 4])
    assert [s.interval_days for s in states] == [1, 6, 15, 1, 1, 6]
    assert [s.repetitions for s in states] == [1, 2, 3, 0, 1, 2]


def test_wrong_answer_still_lowers_ease_factor():
    """答錯只重置間隔與次數，ease 仍照公式下修（下次成長更慢）。"""
    state = review(ItemState(), 0, TODAY)
    assert state.ease_factor == 1.7  # 2.5 − 0.8
    assert state.interval_days == 1


# --- ease_factor 下限 1.3 -----------------------------------------------------


def test_ease_factor_floor_is_locked_at_1_3():
    """quality 0 每次 −0.8：2.5 → 1.7 → 1.3（而非 0.9），之後不再下探。"""
    states = answer_series([0, 0, 0, 0])
    assert [s.ease_factor for s in states] == [1.7, 1.3, 1.3, 1.3]


def test_ease_factor_floor_applies_to_every_quality():
    for quality in range(0, 5):  # quality 5 為 +0.1，不會下探
        assert sc.update_ease_factor(sc.MIN_EASE_FACTOR, quality) >= sc.MIN_EASE_FACTOR


def test_ease_factor_deltas_match_the_formula():
    assert sc.update_ease_factor(2.5, 5) == 2.6  # +0.1
    assert sc.update_ease_factor(2.5, 4) == 2.5  # ±0
    assert sc.update_ease_factor(2.5, 3) == 2.36  # −0.14
    assert sc.update_ease_factor(2.5, 2) == 2.18  # −0.32
    assert sc.update_ease_factor(2.5, 1) == 1.96  # −0.54
    assert sc.update_ease_factor(2.5, 0) == 1.7  # −0.8


def test_ease_factor_has_no_upper_cap():
    """秒答對每次 +0.1，上方不設限（間隔自然拉長即為預期行為）。"""
    ease = sc.DEFAULT_EASE_FACTOR
    for _ in range(10):
        ease = sc.update_ease_factor(ease, 5)
    assert ease == pytest.approx(3.5)


def test_item_state_rejects_ease_below_floor():
    with pytest.raises(SchedulerError):
        ItemState(ease_factor=1.2)


# --- 邊界：quality = 3（剛好及格） -------------------------------------------


def test_quality_three_counts_as_correct():
    """3 是及格線：算答對（間隔往前推），但 ease 下修 0.14。"""
    state = review(ItemState(), 3, TODAY)
    assert state.repetitions == 1
    assert state.interval_days == 1
    assert state.ease_factor == 2.36
    assert state.next_review == "2026-07-31"


def test_quality_three_series_grows_but_slower_than_quality_five():
    threes = answer_series([3, 3, 3])
    fives = answer_series([5, 5, 5])
    assert [s.repetitions for s in threes] == [1, 2, 3]
    assert [s.interval_days for s in threes] == [1, 6, 13]  # round(6 × 2.2196…)
    assert threes[-1].interval_days < fives[-1].interval_days


def test_quality_two_is_the_first_failing_score():
    assert review(ItemState(), 2, TODAY).repetitions == 0
    assert review(ItemState(), 3, TODAY).repetitions == 1


# --- 輸入驗證與工具 -----------------------------------------------------------


@pytest.mark.parametrize("bad", [-1, 6, 2.5, "4", None, True])
def test_invalid_quality_rejected(bad):
    with pytest.raises(SchedulerError):
        review(ItemState(), bad, TODAY)


def test_invalid_date_rejected():
    with pytest.raises(SchedulerError):
        review(ItemState(), 4, "115-06-05")  # 民國年不接受，一律西元 ISO


def test_review_does_not_mutate_input_state():
    original = ItemState()
    review(original, 5, TODAY)
    assert original.ease_factor == 2.5
    assert original.interval_days == 0


def test_new_item_is_due():
    assert sc.is_due(ItemState(), TODAY) is True


def test_scheduled_item_due_only_on_or_after_next_review():
    state = review(ItemState(), 4, TODAY)  # next_review = 07-31
    assert sc.is_due(state, "2026-07-30") is False
    assert sc.is_due(state, "2026-07-31") is True
    assert sc.is_due(state, "2026-08-05") is True


def test_zero_previous_interval_still_advances():
    """資料異常（repetitions 已 2 但 interval 為 0）時不得排出「今天」。"""
    state = review(ItemState(interval_days=0, repetitions=2), 4, TODAY)
    assert state.interval_days >= 1
    assert state.next_review != state.last_reviewed


# --- 批改結果 → 品質分數 -----------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [(25, 5), (23, 5), (22.5, 5), (20, 4), (19, 4), (18.75, 4), (15, 3), (16, 3),
     (14, 2), (10, 2), (9, 1), (5, 1), (4, 0), (0, 0)],
)
def test_quality_from_essay(score, expected):
    assert sc.quality_from_essay(score, 25) == expected


def test_quality_from_essay_passing_line_maps_to_three():
    """15／25＝及格線 → quality 3（剛好及格），與邊界測試呼應。"""
    assert sc.quality_from_essay(15, 25) == sc.PASSING_QUALITY
    assert sc.quality_from_essay(14.9, 25) == 2


def test_quality_from_essay_rejects_out_of_range():
    with pytest.raises(SchedulerError):
        sc.quality_from_essay(30, 25)
    with pytest.raises(SchedulerError):
        sc.quality_from_essay(1, 0)


def test_quality_from_choice():
    assert sc.quality_from_choice(True) == 5
    assert sc.quality_from_choice(True, unsure=True) == 4
    assert sc.quality_from_choice(True, hinted=True) == 3
    assert sc.quality_from_choice(False, partial=True) == 2
    assert sc.quality_from_choice(False) == 1
    assert sc.quality_from_choice(False, blank=True) == 0
    assert sc.quality_from_choice(True, blank=True) == 0
