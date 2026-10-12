"""Scrape Goodreads through the ScrapeUnblocker ``getPageSource`` API.

:class:`GoodreadsScraper` fetches Goodreads pages as rendered HTML and parses them.
Reviews pages are driven with browser ``steps`` (sort, filters, text search and
"Show more reviews"). Timeouts, transient API errors and pages that come back
without their content are retried with doubling backoff, so a long collection
run keeps going.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator, Sequence
from typing import Any, Callable, TypeVar

from .models import (
    Author,
    AuthorBooksPage,
    Book,
    BookDetails,
    BookRow,
    ListPage,
    Review,
    ReviewPage,
    SearchPage,
    ShelfPage,
)
from .parsing import (
    GoodreadsNotFoundError,
    GoodreadsParseError,
    parse_author_books_page,
    parse_author_page,
    parse_book_page,
    parse_list_page,
    parse_reviews_page,
    parse_search_page,
    parse_shelf_page,
)
from .steps import LOAD_MORE, max_review_page, review_steps, step_label
from .urls import (
    author_books_url,
    author_id,
    author_url,
    book_id,
    book_url,
    list_id,
    list_url,
    reviews_url,
    search_url,
    shelf_slug,
    shelf_url,
)

T = TypeVar("T")

_TRANSIENT_NAMES = (
    "UpstreamOutageError",
    "RateLimitError",
    "ScrapeTimeoutError",
    "BrowserTimeoutError",
    "BlockedError",
    "ServerError",
    "ConnectionError",
)
_NOT_FOUND_NAMES = ("TargetNotFoundError", "NotFoundError")

BookRef = Any  # a book ID, a book URL, or a Book / BookRow / BookDetails record


def _transient_errors() -> tuple[type[BaseException], ...]:
    """Best-effort tuple of ScrapeUnblocker exceptions worth retrying.

    Imported lazily so the package is usable (and unit-testable) even when the
    ``scrapeunblocker`` SDK is not installed.
    """
    try:
        import scrapeunblocker  # type: ignore
    except Exception:  # pragma: no cover - depends on SDK availability
        return ()
    found = (getattr(scrapeunblocker, name, None) for name in _TRANSIENT_NAMES)
    return tuple(cls for cls in found if isinstance(cls, type))


def _is_named(error: BaseException, names: Sequence[str]) -> bool:
    return any(cls.__name__ in names for cls in type(error).__mro__)


def _book_number(book: BookRef) -> int:
    number = getattr(book, "book_id", None)
    return int(number) if number is not None else book_id(book)


class GoodreadsScraper:
    """Search Goodreads and read book, review, Listopia, author and shelf pages.

    Args:
        api_key: ScrapeUnblocker key. If omitted, the SDK reads
            ``SCRAPEUNBLOCKER_KEY`` from the environment.
        client: A pre-built client (or any object exposing
            ``get_page_source(url, proxy_country=..., steps=...)``). Mainly for testing.
        country: Optional country to route requests through (``us``, ``gb``, ...).
            By default ScrapeUnblocker picks the route.
        retries: Extra attempts per request on transient failures.
        backoff: Seconds before the first retry; doubles on every further retry.
        max_backoff: Upper bound for a single wait between retries.
        timeout: Per-request timeout passed to the SDK client.
        transient_errors: Exception classes treated as retryable. Defaults to
            the ScrapeUnblocker transient set.
        on_retry: Optional callback ``(attempt, delay_seconds, error)`` invoked
            before every retry (handy for progress output).
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any | None = None,
        country: str | None = None,
        retries: int = 3,
        backoff: float = 5.0,
        max_backoff: float = 60.0,
        timeout: float = 180.0,
        transient_errors: Sequence[type[BaseException]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        on_retry: Callable[[int, float, BaseException], None] | None = None,
    ) -> None:
        if client is None:
            from scrapeunblocker import Client  # local import: optional dep

            client = Client(api_key=api_key, timeout=timeout)
        self._client = client
        self.country = (country or "").strip().lower() or None
        self.retries = max(0, int(retries))
        self.backoff = float(backoff)
        self.max_backoff = float(max_backoff)
        self.on_retry = on_retry
        transient = tuple(transient_errors) if transient_errors is not None else _transient_errors()
        self._transient = (*transient, GoodreadsParseError)
        self._sleep = sleep

    # ------------------------------------------------------------------ #
    # Fetching
    # ------------------------------------------------------------------ #

    def _retry(self, action: Callable[[], T]) -> T:
        """Run ``action``, retrying transient failures with doubling backoff."""
        attempt = 0
        while True:
            try:
                return action()
            except Exception as exc:
                if not isinstance(exc, self._transient) or attempt >= self.retries:
                    raise
                attempt += 1
                delay = min(self.backoff * 2 ** (attempt - 1), self.max_backoff)
                if self.on_retry is not None:
                    self.on_retry(attempt, delay, exc)
                self._sleep(delay)

    def fetch(self, url: str, steps: list[dict[str, Any]] | None = None) -> str:
        """One getPageSource call: the rendered HTML of a Goodreads page.

        ``steps`` are browser actions run after the page loads (see
        :mod:`goodreads_scraper.steps`).
        """
        options: dict[str, Any] = {}
        if self.country:
            options["proxy_country"] = self.country
        if steps:
            options["steps"] = steps
        try:
            html = self._client.get_page_source(url, **options)
        except Exception as exc:
            if _is_named(exc, _NOT_FOUND_NAMES):
                raise GoodreadsNotFoundError(f"Goodreads has no page at {url}") from exc
            raise
        return html if isinstance(html, str) else ""

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def search_page(self, query: str, page: int = 1) -> SearchPage:
        """Fetch one page of book search results (20 books)."""
        target = search_url(query, page)
        return self._retry(lambda: parse_search_page(self.fetch(target), query, page, target))

    def iter_search(
        self,
        query: str,
        *,
        pages: int = 1,
        limit: int | None = None,
        seen: set[int] | None = None,
        min_rating: float | None = None,
        min_ratings: int | None = None,
        one_per_work: bool = False,
        on_page: Callable[[SearchPage], None] | None = None,
    ) -> Iterator[Book]:
        """Yield search results page by page; see :meth:`search` for the arguments."""
        if pages < 1:
            raise ValueError("pages must be at least 1")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        seen = set() if seen is None else seen
        works: set[int] = set()
        yielded = 0
        for number in range(1, pages + 1):
            result = self.search_page(query, number)
            if on_page is not None:
                on_page(result)
            fresh = 0
            for book in result.books:
                if book.book_id in seen:
                    continue
                seen.add(book.book_id)
                fresh += 1
                if min_rating is not None and (book.average_rating or 0) < min_rating:
                    continue
                if min_ratings is not None and (book.ratings_count or 0) < min_ratings:
                    continue
                if one_per_work and book.work_id is not None:
                    if book.work_id in works:
                        continue
                    works.add(book.work_id)
                yield book
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if not result.has_next or fresh == 0:
                return

    def search(
        self,
        query: str,
        *,
        pages: int = 1,
        limit: int | None = None,
        seen: set[int] | None = None,
        min_rating: float | None = None,
        min_ratings: int | None = None,
        one_per_work: bool = False,
        on_page: Callable[[SearchPage], None] | None = None,
    ) -> list[Book]:
        """Search Goodreads books and collect results across pages.

        Args:
            query: Title, author, ISBN or any keywords - as typed in the Goodreads
                search box.
            pages: Pages to fetch (20 books each). Stops early at the last page.
            limit: Return at most this many books.
            seen: Shared set of book IDs; books already in it are skipped. Pass
                the same set to several calls to de-duplicate across searches.
            min_rating: Keep books whose average rating is at least this.
            min_ratings: Keep books with at least this many ratings.
            one_per_work: Keep only the first edition found of each work (Goodreads
                often lists several editions of the same book).
            on_page: Callback invoked with every fetched :class:`SearchPage`.
        """
        return list(
            self.iter_search(
                query,
                pages=pages,
                limit=limit,
                seen=seen,
                min_rating=min_rating,
                min_ratings=min_ratings,
                one_per_work=one_per_work,
                on_page=on_page,
            )
        )

    def search_many(
        self,
        queries: Iterable[str],
        *,
        on_query: Callable[[str, list[Book]], None] | None = None,
        **options: Any,
    ) -> list[Book]:
        """Run :meth:`search` for several queries, merged and de-duplicated by book ID."""
        seen: set[int] = options.pop("seen", None) or set()
        results: list[Book] = []
        for query in queries:
            found = self.search(query, seen=seen, **options)
            if on_query is not None:
                on_query(query, found)
            results.extend(found)
        return results

    # ------------------------------------------------------------------ #
    # Book pages
    # ------------------------------------------------------------------ #

    def book(self, book: BookRef) -> BookDetails:
        """Read a book page: identifiers, edition details, genres, series, awards,
        characters, places, rating histogram, reading stats and the first 30
        community reviews.

        Args:
            book: A book ID (``44767458``), a book URL, or any record with a
                ``book_id`` (a search result, list row, ...).

        Raises:
            GoodreadsNotFoundError: no such book.
        """
        target = book_url(_book_number(book))
        return self._retry(lambda: parse_book_page(self.fetch(target), target))

    def books(
        self,
        items: Iterable[BookRef],
        *,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> list[BookDetails]:
        """Read several book pages; failures go to ``on_error`` (or are raised)."""
        found: list[BookDetails] = []
        for item in items:
            try:
                found.append(self.book(item))
            except Exception as exc:
                if on_error is None:
                    raise
                on_error(str(getattr(item, "url", None) or item), exc)
        return found

    # ------------------------------------------------------------------ #
    # Reviews
    # ------------------------------------------------------------------ #

    def reviews_page(
        self,
        book: BookRef,
        page: int = 1,
        *,
        sort: str = "popular",
        language: str | None = None,
        edition: str = "all",
        rating: int | None = None,
        search: str | None = None,
    ) -> ReviewPage:
        """Fetch one page (30) of a book's community reviews.

        Args:
            book: A book ID, URL or record.
            page: 1-based page. Page ``n`` takes ``n - 1`` clicks on "Show more
                reviews" in the browser, so deeper pages take longer; one request
                reaches :func:`~goodreads_scraper.steps.max_review_page` at most.
            sort: ``popular`` (Goodreads' default), ``newest`` or ``oldest``.
            language: Only reviews in this language (ISO code: ``en``, ``es``,
                ``de``, ``zh-TW``, ...). The book page's ``review_languages``
                lists the languages a book has reviews in.
            edition: ``all`` editions (default) or ``this`` edition only.
            rating: Only reviews with this many stars (1-5).
            search: Only reviews that mention this text.

        Raises:
            ValueError: a filter is invalid or ``page`` is out of reach.
            GoodreadsNotFoundError: no such book, or no reviews in ``language``.
        """
        number = _book_number(book)
        target = reviews_url(number)
        steps = review_steps(
            page, sort=sort, language=language, edition=edition, rating=rating, search=search
        )

        def attempt() -> ReviewPage:
            try:
                html = self.fetch(target, steps or None)
            except Exception as exc:
                if not _is_named(exc, ("StepFailedError",)):
                    raise
                return self._after_failed_step(exc, steps, number, page, target)
            result = parse_reviews_page(html, number, page, target)
            expected = (page - 1) * 30 + 1
            if result.first is not None and result.first != expected:
                raise GoodreadsParseError(
                    f"the reviews page showed reviews {result.first}-{result.last} "
                    f"instead of page {page}"
                )
            return result

        return self._retry(attempt)

    def _after_failed_step(
        self, error: Exception, steps: list[dict[str, Any]], number: int, page: int, url: str
    ) -> ReviewPage:
        index = getattr(error, "step_index", None)
        step = steps[index] if isinstance(index, int) and 0 <= index < len(steps) else {}
        html = getattr(error, "html", None) or ""
        if step.get("selector") == LOAD_MORE:
            shown = parse_reviews_page(html, number, page, url) if html else None
            if shown is not None and shown.total is not None and not shown.has_next:
                # the reviews ran out before this page
                return ReviewPage(book_id=number, page=page, url=url, total=shown.total)
        label = step_label(step) if step else "a browser step"
        if str(step.get("selector", "")).startswith('label[for="'):
            # the sort options always exist, so this is a language with no reviews
            raise GoodreadsNotFoundError(
                f"the review filters have no such option ({label}); the book's "
                "review_languages lists the languages it has reviews in"
            ) from error
        raise GoodreadsParseError(f"could not {label} on {url}: {error}") from error

    def iter_reviews(
        self,
        book: BookRef,
        *,
        pages: int = 1,
        start_page: int = 1,
        limit: int | None = None,
        seen: set[int] | None = None,
        on_page: Callable[[ReviewPage], None] | None = None,
        **filters: Any,
    ) -> Iterator[Review]:
        """Yield reviews page by page; see :meth:`reviews` for the arguments."""
        if pages < 1 or start_page < 1:
            raise ValueError("pages and start_page must be at least 1")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        seen = set() if seen is None else seen
        last = min(start_page + pages - 1, max_review_page(**filters))
        yielded = 0
        for number in range(start_page, last + 1):
            result = self.reviews_page(book, number, **filters)
            if on_page is not None:
                on_page(result)
            fresh = 0
            for review in result.reviews:
                key = review.review_id or hash((review.reviewer_id, review.date, review.text))
                if key in seen:
                    continue
                seen.add(key)
                fresh += 1
                yield review
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if not result.has_next or fresh == 0:
                return

    def reviews(
        self,
        book: BookRef,
        *,
        pages: int = 1,
        start_page: int = 1,
        limit: int | None = None,
        seen: set[int] | None = None,
        on_page: Callable[[ReviewPage], None] | None = None,
        **filters: Any,
    ) -> list[Review]:
        """Collect a book's community reviews across pages (30 per page).

        Args:
            book: A book ID, URL or record.
            pages: Pages to fetch from ``start_page`` on. Collection stops at the
                last page of reviews, and at the deepest page one request can
                reach with these filters (see
                :func:`~goodreads_scraper.steps.max_review_page`).
            start_page: First page to fetch.
            limit: Return at most this many reviews.
            seen: Shared set of review IDs to skip (de-duplicates across calls).
            on_page: Callback invoked with every fetched :class:`ReviewPage`.
            **filters: ``sort``, ``language``, ``edition``, ``rating`` and
                ``search``; see :meth:`reviews_page`.
        """
        return list(
            self.iter_reviews(
                book,
                pages=pages,
                start_page=start_page,
                limit=limit,
                seen=seen,
                on_page=on_page,
                **filters,
            )
        )

    # ------------------------------------------------------------------ #
    # Listopia
    # ------------------------------------------------------------------ #

    def listopia_page(self, listing: str | int, page: int = 1) -> ListPage:
        """Fetch one page (100 books) of a Listopia list, with the list's details.

        Raises:
            GoodreadsNotFoundError: no such list.
        """
        number = list_id(listing)
        target = list_url(number, page)
        return self._retry(lambda: parse_list_page(self.fetch(target), number, page, target))

    def iter_listopia(
        self,
        listing: str | int,
        *,
        pages: int = 1,
        limit: int | None = None,
        on_page: Callable[[ListPage], None] | None = None,
    ) -> Iterator[BookRow]:
        """Yield the books of a Listopia list in rank order, page by page."""
        if pages < 1:
            raise ValueError("pages must be at least 1")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        seen: set[int] = set()
        yielded = 0
        for number in range(1, pages + 1):
            result = self.listopia_page(listing, number)
            if on_page is not None:
                on_page(result)
            fresh = 0
            for book in result.books:
                if book.book_id in seen:
                    continue
                seen.add(book.book_id)
                fresh += 1
                yield book
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if not result.has_next or fresh == 0:
                return

    def listopia(
        self,
        listing: str | int,
        *,
        pages: int = 1,
        limit: int | None = None,
        on_page: Callable[[ListPage], None] | None = None,
    ) -> list[BookRow]:
        """Collect the books of a Listopia list (100 per page) with rank, score and votes.

        Args:
            listing: A list ID (``1``), its slug (``1.Best_Books_Ever``) or URL.
            pages: Pages to fetch. Stops early at the last page.
            limit: Return at most this many books.
            on_page: Callback invoked with every fetched :class:`ListPage`.
        """
        return list(self.iter_listopia(listing, pages=pages, limit=limit, on_page=on_page))

    # ------------------------------------------------------------------ #
    # Authors
    # ------------------------------------------------------------------ #

    def author(self, author: str | int) -> Author:
        """Read an author profile: born/died, birthplace, website, genres, bio,
        rating stats, distinct works and the most popular books.

        Raises:
            GoodreadsNotFoundError: no such author.
        """
        number = author_id(author)
        target = author_url(number)
        return self._retry(lambda: parse_author_page(self.fetch(target), number, target))

    def author_books_page(
        self, author: str | int, page: int = 1, sort: str | None = None
    ) -> AuthorBooksPage:
        """Fetch one page (30 books) of an author's full book list.

        ``sort`` is ``popularity`` (default), ``published`` (newest first),
        ``title``, ``rating`` or ``pages``.
        """
        number = author_id(author)
        target = author_books_url(number, page, sort)
        return self._retry(
            lambda: parse_author_books_page(self.fetch(target), number, page, target, sort)
        )

    def iter_author_books(
        self,
        author: str | int,
        *,
        pages: int = 1,
        sort: str | None = None,
        limit: int | None = None,
        on_page: Callable[[AuthorBooksPage], None] | None = None,
    ) -> Iterator[BookRow]:
        """Yield an author's books page by page."""
        if pages < 1:
            raise ValueError("pages must be at least 1")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        seen: set[int] = set()
        yielded = 0
        for number in range(1, pages + 1):
            result = self.author_books_page(author, number, sort)
            if on_page is not None:
                on_page(result)
            fresh = 0
            for book in result.books:
                if book.book_id in seen:
                    continue
                seen.add(book.book_id)
                fresh += 1
                yield book
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if not result.has_next or fresh == 0:
                return

    def author_books(
        self,
        author: str | int,
        *,
        pages: int = 1,
        sort: str | None = None,
        limit: int | None = None,
        on_page: Callable[[AuthorBooksPage], None] | None = None,
    ) -> list[BookRow]:
        """Collect an author's books (30 per page): title, series, co-authors,
        rating, ratings, first-published year and edition count.

        Args:
            author: An author ID (``58``), its slug (``58.Frank_Herbert``) or URL.
            pages: Pages to fetch. Stops early at the last page.
            sort: ``popularity`` (default), ``published``, ``title``, ``rating``
                or ``pages``.
            limit: Return at most this many books.
            on_page: Callback invoked with every fetched :class:`AuthorBooksPage`.
        """
        return list(
            self.iter_author_books(author, pages=pages, sort=sort, limit=limit, on_page=on_page)
        )

    # ------------------------------------------------------------------ #
    # Shelves
    # ------------------------------------------------------------------ #

    def shelf(self, shelf: str) -> ShelfPage:
        """The most-shelved books for a shelf / genre tag (``fantasy``,
        ``science-fiction``, ``historical-fiction``, ...), with how many readers
        shelved each one under that tag.
        """
        slug = shelf_slug(shelf)
        target = shelf_url(slug)
        return self._retry(lambda: parse_shelf_page(self.fetch(target), slug, target))


__all__ = ["GoodreadsScraper"]
