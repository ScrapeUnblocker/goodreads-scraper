from __future__ import annotations

import pytest

from goodreads_scraper import GoodreadsNotFoundError, GoodreadsParseError
from goodreads_scraper.models import Book
from goodreads_scraper.steps import LOAD_MORE, READY

from .conftest import (
    StepFailedError,
    TargetNotFoundError,
    _search_book,
    author_books_html,
    author_html,
    book_html,
    book_row,
    list_html,
    reviews_html,
    search_html,
    sequence,
    shelf_html,
)

# --------------------------------------------------------------------------- #
# Fetching and retries
# --------------------------------------------------------------------------- #


def test_fetch_passes_country_and_steps(make_scraper):
    scraper, client = make_scraper(sequence("<html></html>"), country=" US ")
    scraper.fetch("https://www.goodreads.com/x", steps=[{"action": "wait", "value": 1}])
    assert client.calls == [
        (
            "https://www.goodreads.com/x",
            {"proxy_country": "us", "steps": [{"action": "wait", "value": 1}]},
        )
    ]


def test_retries_a_page_that_came_back_empty(make_scraper):
    waits = []
    retries = []
    scraper, client = make_scraper(
        sequence("<html>Just a moment...</html>", search_html()),
        sleep=waits.append,
        on_retry=lambda attempt, delay, error: retries.append((attempt, delay)),
    )
    page = scraper.search_page("dune")
    assert len(page.books) == 3
    assert len(client.calls) == 2
    assert waits == [5.0] and retries == [(1, 5.0)]


def test_retries_transient_api_errors_with_doubling_backoff(make_scraper):
    waits = []
    scraper, client = make_scraper(
        sequence(TimeoutError("slow"), TimeoutError("slow"), search_html()), sleep=waits.append
    )
    scraper.search_page("dune")
    assert waits == [5.0, 10.0]


def test_gives_up_after_the_retry_budget(make_scraper):
    scraper, client = make_scraper(sequence(TimeoutError("slow")), retries=2)
    with pytest.raises(TimeoutError):
        scraper.search_page("dune")
    assert len(client.calls) == 3


def test_404_becomes_not_found_without_retrying(make_scraper):
    scraper, client = make_scraper(sequence(TargetNotFoundError("404")))
    with pytest.raises(GoodreadsNotFoundError):
        scraper.author(999999999)
    assert len(client.calls) == 1


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #


def full_page(start: int) -> str:
    books = [_search_book(start + i, f"Book {start + i}", start + i) for i in range(20)]
    return search_html(books=books, total="45", first=start)


def test_search_collects_pages_until_a_short_page(make_scraper):
    def handler(url, options):
        if "page=2" in url:
            return full_page(200)
        if "page=3" in url:
            return search_html()  # 3 books: the last page
        return full_page(100)

    pages = []
    scraper, client = make_scraper(handler)
    books = scraper.search("dune", pages=5, on_page=pages.append)
    assert len(books) == 43
    assert [p.page for p in pages] == [1, 2, 3]
    assert len(client.calls) == 3
    assert client.calls[0][0] == "https://www.goodreads.com/search?q=dune&search_type=books"


def test_search_limit_and_filters(make_scraper):
    scraper, _ = make_scraper(sequence(search_html()))
    assert [b.book_id for b in scraper.search("dune", limit=1)] == [44767458]
    assert [b.book_id for b in scraper.search("dune", min_rating=4.0)] == [44767458, 1111]
    assert [b.book_id for b in scraper.search("dune", min_ratings=500000)] == [44767458, 1111]
    assert [b.book_id for b in scraper.search("dune", one_per_work=True)] == [44767458, 44492285]


def test_search_many_dedupes_across_queries(make_scraper):
    seen_queries = []
    scraper, client = make_scraper(sequence(search_html()))
    books = scraper.search_many(
        ["dune", "frank herbert"], on_query=lambda q, found: seen_queries.append((q, len(found)))
    )
    assert len(books) == 3
    assert seen_queries == [("dune", 3), ("frank herbert", 0)]


def test_search_rejects_bad_arguments(make_scraper):
    scraper, _ = make_scraper(sequence(search_html()))
    with pytest.raises(ValueError):
        scraper.search("dune", pages=0)
    with pytest.raises(ValueError):
        scraper.search("dune", limit=0)


# --------------------------------------------------------------------------- #
# Books
# --------------------------------------------------------------------------- #


def test_book_accepts_ids_urls_and_records(make_scraper):
    scraper, client = make_scraper(sequence(book_html()))
    scraper.book("https://www.goodreads.com/book/show/44767458-dune")
    scraper.book(Book(book_id=44767458, title="Dune", url="u"))
    details = scraper.book(44767458)
    assert details.isbn13 == "9780593099322"
    assert {url for url, _ in client.calls} == {"https://www.goodreads.com/book/show/44767458"}


def test_books_reports_failures(make_scraper):
    def handler(url, options):
        return TargetNotFoundError("404") if url.endswith("/1") else book_html()

    failures = []
    scraper, _ = make_scraper(handler)
    found = scraper.books([1, 44767458], on_error=lambda item, exc: failures.append(item))
    assert [b.book_id for b in found] == [44767458]
    assert failures == ["1"]


# --------------------------------------------------------------------------- #
# Reviews
# --------------------------------------------------------------------------- #


def test_first_review_page_is_a_plain_request(make_scraper):
    scraper, client = make_scraper(sequence(reviews_html()))
    page = scraper.reviews_page("44767458-dune")
    assert len(page.reviews) == 30
    assert client.calls == [("https://www.goodreads.com/book/show/44767458/reviews", {})]


def test_review_filters_and_paging_become_steps(make_scraper):
    scraper, client = make_scraper(sequence(reviews_html(first=61, filters=["Newest first"])))
    page = scraper.reviews_page(44767458, 3, sort="newest", rating=1)
    assert page.first == 61
    steps = client.calls[0][1]["steps"]
    assert [s.get("selector") for s in steps] == [
        ".ReviewFilters__filters button",
        'label[for="NEWEST"]',
        ".Overlay__actions .Button--primary",
        '[data-testid="ratingBar-1"]',
        READY,
        LOAD_MORE,
        LOAD_MORE,
        READY,
    ]


def test_landing_on_the_wrong_review_page_is_retried(make_scraper):
    scraper, client = make_scraper(sequence(reviews_html(first=31), reviews_html(first=61)))
    page = scraper.reviews_page(1, 3)
    assert page.first == 61 and len(client.calls) == 2


def test_running_out_of_reviews_returns_an_empty_page(make_scraper):
    last_page = reviews_html(first=31, total="45", cards=None)
    scraper, client = make_scraper(sequence(StepFailedError(1, html=last_page)))
    page = scraper.reviews_page(1, 3)
    assert page.reviews == [] and page.total == 45 and not page.has_next
    assert len(client.calls) == 1


def test_unknown_review_language_is_not_found(make_scraper):
    scraper, client = make_scraper(sequence(StepFailedError(1)))
    with pytest.raises(GoodreadsNotFoundError, match="review_languages"):
        scraper.reviews_page(1, language="xx")
    assert len(client.calls) == 1


def test_other_step_failures_are_retried(make_scraper):
    scraper, client = make_scraper(sequence(StepFailedError(0), reviews_html(first=31)))
    page = scraper.reviews_page(1, 2)
    assert page.first == 31 and len(client.calls) == 2


def test_step_failures_give_up_as_parse_errors(make_scraper):
    scraper, _ = make_scraper(sequence(StepFailedError(0)), retries=1)
    with pytest.raises(GoodreadsParseError, match="show more reviews"):
        scraper.reviews_page(1, 2)


def test_iter_reviews_pages_and_dedupes(make_scraper):
    def handler(url, options):
        clicks = sum(1 for s in options.get("steps", []) if s.get("selector") == LOAD_MORE)
        return reviews_html(first=clicks * 30 + 1, total="75")

    scraper, client = make_scraper(handler)
    reviews = scraper.reviews(1, pages=5)
    assert len(reviews) == 90  # three pages: 1-30, 31-60, 61-90 (the last says 75 in total)
    assert len(client.calls) == 3
    assert len({r.review_id for r in reviews}) == 90


def test_iter_reviews_stops_at_the_step_budget(make_scraper):
    def handler(url, options):
        clicks = sum(1 for s in options.get("steps", []) if s.get("selector") == LOAD_MORE)
        return reviews_html(first=clicks * 30 + 1, total="9,999")

    scraper, client = make_scraper(handler)
    reviews = scraper.reviews(1, pages=50, sort="newest")
    assert len(client.calls) == 6
    assert len(reviews) == 180


def test_reviews_limit_and_start_page(make_scraper):
    def handler(url, options):
        clicks = sum(1 for s in options.get("steps", []) if s.get("selector") == LOAD_MORE)
        return reviews_html(first=clicks * 30 + 1, total="9,999")

    scraper, client = make_scraper(handler)
    reviews = scraper.reviews(1, start_page=2, pages=3, limit=40)
    assert len(reviews) == 40 and reviews[0].position == 31
    assert len(client.calls) == 2


# --------------------------------------------------------------------------- #
# Listopia, authors, shelves
# --------------------------------------------------------------------------- #


def test_listopia_follows_pages(make_scraper):
    def handler(url, options):
        page = int(url.split("page=")[1]) if "page=" in url else 1
        rows = None
        if page > 1:
            rows = [book_row(5000 + page, f"Book {page}", rank=(page - 1) * 100 + 1)]
        return list_html(page=page, last_page=2, rows=rows)

    pages = []
    scraper, client = make_scraper(handler)
    books = scraper.listopia("1.Best_Books_Ever", pages=10, on_page=pages.append)
    assert [b.rank for b in books] == [1, 2, 101]
    assert [url for url, _ in client.calls] == [
        "https://www.goodreads.com/list/show/1",
        "https://www.goodreads.com/list/show/1?page=2",
    ]
    assert pages[0].title == "Best Books Ever"


def test_listopia_stops_when_a_page_repeats(make_scraper):
    scraper, client = make_scraper(sequence(list_html(last_page=5)))
    assert len(scraper.listopia(1, pages=5)) == 2
    assert len(client.calls) == 2


def test_author_and_author_books(make_scraper):
    def handler(url, options):
        if "/author/list/" in url:
            return author_books_html(page=2 if "page=2" in url else 1)
        return author_html()

    scraper, client = make_scraper(handler)
    author = scraper.author("https://www.goodreads.com/author/show/58.Frank_Herbert")
    assert author.name == "Frank Herbert" and author.works_count == 636
    books = scraper.author_books(58, pages=3, sort="rating")
    assert len(books) == 4
    assert client.calls[1][0].endswith("/author/list/58?page=1&per_page=30&sort=average_rating")
    assert len(client.calls) == 3


def test_shelf(make_scraper):
    scraper, client = make_scraper(sequence(shelf_html()))
    page = scraper.shelf("Science Fiction")
    assert page.shelf == "science-fiction" and page.books[0].shelved_count == 22035
    assert client.calls[0][0] == "https://www.goodreads.com/shelf/show/science-fiction"
