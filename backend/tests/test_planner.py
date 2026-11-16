from datetime import date, time

from app.services.planner import Block, Slot, Task, diff, full_weekdays, generate, prep_days

TODAY = date(2026, 10, 1)
TERM_END = date(2026, 12, 22)
COOP = [Slot(d, time(9), time(17)) for d in (0, 1, 3)]  # Mon, Tue, Thu full days
TASKS = [
    Task(1, "COMP 6481", "Midterm", "midterm", date(2026, 10, 20), 25),
    Task(2, "COMP 6231", "Milestone 2", "project", date(2026, 10, 22), 15),
    Task(3, "COMP 6721", "Assignment 2", "assignment", date(2026, 10, 23), 10),
]


def test_full_weekdays_threshold():
    slots = COOP + [Slot(2, time(13), time(16))]  # Wed 3 h is not full
    assert full_weekdays(slots, 8) == {0, 1, 3}


def test_prep_days_rules():
    assert prep_days(TASKS[0]) == 5          # 25 / 5
    assert prep_days(Task(9, "X", "Quiz", "midterm", TODAY, 5)) == 3  # exams at least 3
    assert prep_days(Task(9, "X", "Lab", "lab", TODAY, None)) == 1
    assert prep_days(Task(9, "X", "Big", "project", TODAY, 80)) == 7


def test_plan_is_valid_and_avoids_full_days():
    result = generate(TASKS, COOP, TODAY, TERM_END)
    assert result.is_valid, result.errors
    for b in result.blocks:
        d = b.start
        while d <= b.end:
            assert d.weekday() not in {0, 1, 3}
            d = date.fromordinal(d.toordinal() + 1)
    for t in TASKS:
        assert any(b.assessment_id == t.id and b.end < t.due for b in result.blocks)


def test_cap_of_two_blocks_per_day():
    result = generate(TASKS, COOP, TODAY, TERM_END)
    load = {}
    for b in result.blocks:
        d = b.start
        while d <= b.end:
            load[d] = load.get(d, 0) + 1
            d = date.fromordinal(d.toordinal() + 1)
    assert max(load.values()) <= 2


def test_impossible_plan_is_flagged_not_hidden():
    every_day = [Slot(d, time(8), time(18)) for d in range(7)]
    result = generate(TASKS, every_day, TODAY, TERM_END)
    assert result.blocks == [] and len(result.warnings) == 3  # nothing the planner could do


def test_cap_too_tight_makes_plan_invalid():
    # only Saturdays free, five tasks due the same Monday, cap 1 then 2: cannot fit
    tasks = [Task(i, "C", f"T{i}", "assignment", date(2026, 10, 5), 5) for i in range(1, 6)]
    weekdays_full = [Slot(d, time(8), time(18)) for d in (0, 1, 2, 3, 4, 6)]
    result = generate(tasks, weekdays_full, TODAY, TERM_END, max_per_day=1)
    assert not result.is_valid and result.errors


def test_past_deadlines_are_ignored():
    result = generate([Task(1, "X", "Old", "assignment", date(2026, 9, 20), 10)], [], TODAY, TERM_END)
    assert result.blocks == [] and result.is_valid


def test_adding_a_shift_moves_blocks_in_diff():
    before = generate(TASKS, COOP, TODAY, TERM_END).blocks
    after = generate(TASKS, COOP + [Slot(4, time(9), time(17))], TODAY, TERM_END).blocks  # Friday now full
    d = diff(before, after)
    assert d["moved"], d
    assert all(date.fromisoformat(r["start"]).weekday() != 4 for m in d["moved"] for r in m["now"])


def test_diff_added_and_removed():
    old = [Block(1, "a", date(2026, 10, 5), date(2026, 10, 6))]
    new = [Block(2, "b", date(2026, 10, 7), date(2026, 10, 7))]
    d = diff(old, new)
    assert [x["assessment_id"] for x in d["removed"]] == [1]
    assert [x["assessment_id"] for x in d["added"]] == [2]
