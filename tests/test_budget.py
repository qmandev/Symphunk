import pytest
from symphunk.harness.budget import SearchBudget, BudgetExhausted


def test_budget_counts_correctly():
    b = SearchBudget(max_searches=3)
    b.check()
    b.check()
    b.check()
    with pytest.raises(BudgetExhausted):
        b.check()


def test_remaining_decrements():
    b = SearchBudget(max_searches=5)
    assert b.remaining == 5
    b.check()
    assert b.remaining == 4


def test_time_bounds_capped_at_7_days():
    from datetime import datetime, timezone
    early, late = SearchBudget.time_bounds(days=100)
    earliest = datetime.fromisoformat(early).replace(tzinfo=timezone.utc)
    latest = datetime.fromisoformat(late).replace(tzinfo=timezone.utc)
    assert (latest - earliest).days <= 7


def test_time_bounds_respects_requested_days():
    from datetime import datetime, timezone
    early, late = SearchBudget.time_bounds(days=1)
    earliest = datetime.fromisoformat(early).replace(tzinfo=timezone.utc)
    latest = datetime.fromisoformat(late).replace(tzinfo=timezone.utc)
    assert (latest - earliest).days <= 1
