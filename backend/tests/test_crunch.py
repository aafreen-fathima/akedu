from datetime import date

from app.services.crunch import Item, detect

D = date


def test_three_items_in_seven_days_flags():
    items = [Item(1, D(2026, 10, 20), 2), Item(2, D(2026, 10, 22), 2), Item(3, D(2026, 10, 26), 2)]
    [p] = detect(items)
    assert (p.start, p.end, p.count) == (D(2026, 10, 20), D(2026, 10, 26), 3)
    assert "3 assessments" in p.reasons[0]


def test_day_seven_boundary():
    # 20th + 6 days = 26th is inside; 27th is outside
    items = [Item(1, D(2026, 10, 20), 1), Item(2, D(2026, 10, 22), 1), Item(3, D(2026, 10, 27), 1)]
    assert detect(items) == []


def test_weight_rule_alone_flags():
    items = [Item(1, D(2026, 10, 20), 25), Item(2, D(2026, 10, 23), 10)]
    [p] = detect(items)
    assert p.total_weight == 35 and p.count == 2
    assert any("35% combined weight" in r for r in p.reasons)


def test_sara_45_percent_in_3_days():
    items = [Item(1, D(2026, 11, 2), 15), Item(2, D(2026, 11, 3), 15), Item(3, D(2026, 11, 4), 15)]
    [p] = detect(items)
    assert p.total_weight == 45 and len(p.reasons) == 2


def test_missing_weight_counts_but_adds_zero():
    items = [Item(1, D(2026, 10, 1), None), Item(2, D(2026, 10, 2), None), Item(3, D(2026, 10, 3), None)]
    [p] = detect(items)
    assert p.total_weight == 0 and p.count == 3


def test_overlapping_windows_merge_and_separate_periods_stay_apart():
    items = [Item(i, D(2026, 10, d), 12) for i, d in enumerate([1, 3, 8, 9], start=1)]
    items += [Item(9, D(2026, 12, 1), 40)]
    periods = detect(items)
    assert len(periods) == 2
    assert periods[0].assessment_ids == [2, 3, 4]  # Oct 1's own window holds only 24%
    assert periods[1].assessment_ids == [9]


def test_quiet_semester_has_no_flags():
    assert detect([Item(1, D(2026, 9, 10), 10), Item(2, D(2026, 10, 10), 10)]) == []
