from __future__ import annotations

import pytest

from goodreads_scraper.steps import (
    LOAD_MORE,
    MAX_STEPS,
    READY,
    filter_steps,
    max_review_page,
    review_steps,
    step_label,
)


def test_first_page_without_filters_needs_no_steps():
    assert review_steps() == []
    assert filter_steps() == []


def test_deeper_pages_click_show_more_then_wait():
    steps = review_steps(3)
    assert [s.get("selector") for s in steps] == [LOAD_MORE, LOAD_MORE, READY]
    assert steps[-1]["action"] == "wait_for"


def test_filters_open_the_dialog_once():
    steps = filter_steps(sort="newest", language="en", edition="this", rating=1, search="spice")
    selectors = [s.get("selector") for s in steps]
    assert selectors[0] == ".ReviewFilters__filters button"
    assert 'label[for="NEWEST"]' in selectors
    assert 'label[for="en"]' in selectors
    assert '[aria-label="Edition"] label:not([for="all-editions"])' in selectors
    assert selectors.index(".Overlay__actions .Button--primary") > selectors.index(
        'label[for="en"]'
    )
    assert '[data-testid="ratingBar-1"]' in selectors
    assert steps[-2] == {
        "action": "type",
        "selector": 'input[placeholder="Search review text"]',
        "value": "spice",
    }
    assert steps[-1] == {"action": "press_key", "value": "Enter"}


def test_rating_only_skips_the_dialog():
    assert filter_steps(rating=5) == [
        {"action": "click", "selector": '[data-testid="ratingBar-5"]'}
    ]


def test_filtered_page_waits_before_and_after_paging():
    steps = review_steps(2, sort="oldest")
    actions = [s["action"] for s in steps]
    assert actions == ["click", "click", "click", "wait_for", "click", "wait_for"]


def test_step_budget():
    assert max_review_page() == MAX_STEPS
    assert len(review_steps(max_review_page())) == MAX_STEPS
    assert max_review_page(sort="newest") == 6
    assert len(review_steps(6, sort="newest")) == MAX_STEPS
    with pytest.raises(ValueError, match="out of reach"):
        review_steps(7, sort="newest")
    everything = {"sort": "newest", "language": "en", "rating": 2, "search": "x"}
    assert max_review_page(**everything) == 2


@pytest.mark.parametrize(
    "bad",
    [
        {"sort": "best"},
        {"language": "English"},
        {"edition": "first"},
        {"rating": 6},
        {"search": "  "},
    ],
)
def test_invalid_filters(bad):
    with pytest.raises(ValueError):
        filter_steps(**bad)


def test_page_must_be_positive():
    with pytest.raises(ValueError):
        review_steps(0)


def test_step_labels():
    assert step_label({"action": "click", "selector": LOAD_MORE}) == "show more reviews"
    assert "en" in step_label({"action": "click", "selector": 'label[for="en"]'})
    assert step_label({"action": "wait_for", "selector": READY}) == "wait for the reviews"
