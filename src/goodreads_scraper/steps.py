"""Browser steps that drive a Goodreads reviews page.

The reviews page (``/book/show/<id>/reviews``) shows 30 reviews at a time. Sorting,
the language and edition filters, the star-rating filter, the review text search and
"Show more reviews" all happen in the browser, so they are sent to the
ScrapeUnblocker ``getPageSource`` API as ``steps`` that run after the page loads.
"Show more reviews" replaces the 30 reviews on screen with the next 30, so review
page ``n`` is ``n - 1`` clicks on that button.

A request runs at most :data:`MAX_STEPS` steps, which caps how deep one request can
page; :func:`max_review_page` tells you the deepest page for a set of filters.
"""

from __future__ import annotations

import re
from typing import Any

#: The most browser steps one getPageSource request accepts.
MAX_STEPS = 10

#: Review sort orders: our name -> the option on the Goodreads filter dialog.
REVIEW_SORTS = {"popular": "DEFAULT", "newest": "NEWEST", "oldest": "OLDEST"}
#: Which editions' reviews to show.
REVIEW_EDITIONS = ("all", "this")

FILTERS_BUTTON = ".ReviewFilters__filters button"
APPLY_BUTTON = ".Overlay__actions .Button--primary"
THIS_EDITION = '[aria-label="Edition"] label:not([for="all-editions"])'
SEARCH_INPUT = 'input[placeholder="Search review text"]'
LOAD_MORE = '[data-testid="loadMore"]'
#: Matches once the review list has rendered (or says nothing matches the filters).
READY = 'article.ReviewCard, [data-testid="error-card"]'
READY_TIMEOUT_MS = 20000

_LANGUAGE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")


def _check(
    sort: str, language: str | None, edition: str, rating: int | None, search: str | None
) -> None:
    if sort not in REVIEW_SORTS:
        raise ValueError(f"unknown review sort {sort!r}; choose one of: {', '.join(REVIEW_SORTS)}")
    if language is not None and not _LANGUAGE.match(language):
        raise ValueError(f"language must be an ISO code such as en, es or zh-TW, not {language!r}")
    if edition not in REVIEW_EDITIONS:
        raise ValueError(f"edition must be one of: {', '.join(REVIEW_EDITIONS)}")
    if rating is not None and rating not in (1, 2, 3, 4, 5):
        raise ValueError("rating must be a whole number of stars from 1 to 5")
    if search is not None and not search.strip():
        raise ValueError("the review search text is empty")


def filter_steps(
    *,
    sort: str = "popular",
    language: str | None = None,
    edition: str = "all",
    rating: int | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Steps that apply the filters (empty when every filter is at its default)."""
    _check(sort, language, edition, rating, search)
    steps: list[dict[str, Any]] = []
    dialog: list[dict[str, Any]] = []
    if sort != "popular":
        dialog.append({"action": "click", "selector": f'label[for="{REVIEW_SORTS[sort]}"]'})
    if edition == "this":
        dialog.append({"action": "click", "selector": THIS_EDITION})
    if language:
        dialog.append({"action": "click", "selector": f'label[for="{language}"]'})
    if dialog:
        steps.append({"action": "click", "selector": FILTERS_BUTTON})
        steps.extend(dialog)
        steps.append({"action": "click", "selector": APPLY_BUTTON})
    if rating is not None:
        steps.append({"action": "click", "selector": f'[data-testid="ratingBar-{rating}"]'})
    if search is not None:
        steps.append({"action": "type", "selector": SEARCH_INPUT, "value": search.strip()})
        steps.append({"action": "press_key", "value": "Enter"})
    return steps


def _ready() -> dict[str, Any]:
    return {"action": "wait_for", "selector": READY, "timeout_ms": READY_TIMEOUT_MS}


def review_steps(page: int = 1, **filters: Any) -> list[dict[str, Any]]:
    """The full step list for one page of reviews with the given filters.

    ``filters`` are ``sort``, ``language``, ``edition``, ``rating`` and ``search``
    (see :func:`filter_steps`). Returns an empty list for page 1 without filters.

    Raises:
        ValueError: a filter value is invalid, or ``page`` is deeper than one
            request can reach with these filters (see :func:`max_review_page`).
    """
    if page < 1:
        raise ValueError("page must be at least 1")
    steps = filter_steps(**filters)
    if steps:
        steps.append(_ready())
    if page > 1:
        steps.extend({"action": "click", "selector": LOAD_MORE} for _ in range(page - 1))
        steps.append(_ready())
    if len(steps) > MAX_STEPS:
        deepest = max_review_page(**filters)
        raise ValueError(
            f"review page {page} is out of reach with these filters: one request runs at most "
            f"{MAX_STEPS} browser steps, which reaches page {deepest}"
        )
    return steps


def max_review_page(**filters: Any) -> int:
    """The deepest review page one request can reach with these filters."""
    used = len(filter_steps(**filters))
    if used:
        used += 1  # wait for the filtered list
    # page n adds n - 1 "show more" clicks and one final wait
    return max(1, MAX_STEPS - used)


def step_label(step: dict[str, Any]) -> str:
    """A human description of a step, for error messages."""
    selector = step.get("selector", "")
    if selector == LOAD_MORE:
        return "show more reviews"
    if selector == FILTERS_BUTTON:
        return "open the review filters"
    if selector == APPLY_BUTTON:
        return "apply the review filters"
    if selector.startswith("label[for="):
        return f"pick the {selector[len('label[for=') : -1]} filter option"
    if selector == THIS_EDITION:
        return "pick this edition"
    if selector.startswith('[data-testid="ratingBar-'):
        return "filter by star rating"
    if selector == SEARCH_INPUT or step.get("action") == "press_key":
        return "search the review text"
    if step.get("action") == "wait_for":
        return "wait for the reviews"
    return str(step.get("action", "step"))


__all__ = [
    "LOAD_MORE",
    "MAX_STEPS",
    "READY",
    "REVIEW_EDITIONS",
    "REVIEW_SORTS",
    "filter_steps",
    "max_review_page",
    "review_steps",
    "step_label",
]
