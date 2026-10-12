"""Goodreads URLs: build them from IDs, and read IDs back out of any Goodreads link.

Every function that takes a book, author or list accepts the bare ID (``44767458``),
the ID with its slug as Goodreads prints it (``44767458-dune``, ``58.Frank_Herbert``,
``1.Best_Books_Ever``) or a full URL copied from the browser.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus, urlencode

BASE_URL = "https://www.goodreads.com"

#: Books per search results page.
SEARCH_PAGE_SIZE = 20
#: Books per Listopia list page.
LIST_PAGE_SIZE = 100
#: Books per page of an author's book list.
AUTHOR_BOOKS_PAGE_SIZE = 30

#: Sort orders of an author's book list: our name -> Goodreads ``sort`` value.
AUTHOR_BOOK_SORTS = {
    "popularity": "popularity",
    "published": "original_publication_year",
    "title": "title",
    "rating": "average_rating",
    "pages": "number_of_pages",
}

_PATTERNS = {
    "book": re.compile(r"/book/show/(\d+)"),
    "author": re.compile(r"/author/(?:show|list)/(\d+)"),
    "list": re.compile(r"/list/show/(\d+)"),
}
_LEADING_ID = re.compile(r"^(\d+)(?:[-._].*)?$")
_SHELF_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _extract_id(value: str | int, kind: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"not a Goodreads {kind} ID: {value!r}")
    if isinstance(value, int):
        if value < 1:
            raise ValueError(f"not a Goodreads {kind} ID: {value!r}")
        return value
    text = str(value).strip()
    match = _PATTERNS[kind].search(text) or _LEADING_ID.match(text)
    if not match:
        raise ValueError(f"not a Goodreads {kind} ID or URL: {value!r}")
    return int(match.group(1))


def book_id(value: str | int) -> int:
    """The numeric book ID from ``44767458``, ``44767458-dune`` or a book URL."""
    return _extract_id(value, "book")


def author_id(value: str | int) -> int:
    """The numeric author ID from ``58``, ``58.Frank_Herbert`` or an author URL."""
    return _extract_id(value, "author")


def list_id(value: str | int) -> int:
    """The numeric Listopia list ID from ``1``, ``1.Best_Books_Ever`` or a list URL."""
    return _extract_id(value, "list")


def search_url(query: str, page: int = 1) -> str:
    """The URL of one page of Goodreads book search results."""
    query = " ".join(str(query).split())
    if not query:
        raise ValueError("the search query is empty")
    if page < 1:
        raise ValueError("page must be at least 1")
    url = f"{BASE_URL}/search?q={quote_plus(query)}&search_type=books"
    return url if page == 1 else f"{url}&page={page}"


def book_url(value: str | int) -> str:
    """The book page URL."""
    return f"{BASE_URL}/book/show/{book_id(value)}"


def reviews_url(value: str | int) -> str:
    """The URL of a book's community reviews page."""
    return f"{book_url(value)}/reviews"


def list_url(value: str | int, page: int = 1) -> str:
    """The URL of one page of a Listopia list (100 books per page)."""
    if page < 1:
        raise ValueError("page must be at least 1")
    url = f"{BASE_URL}/list/show/{list_id(value)}"
    return url if page == 1 else f"{url}?page={page}"


def author_url(value: str | int) -> str:
    """The author profile URL."""
    return f"{BASE_URL}/author/show/{author_id(value)}"


def author_books_url(value: str | int, page: int = 1, sort: str | None = None) -> str:
    """The URL of one page (30 books) of an author's full book list.

    ``sort`` is one of :data:`AUTHOR_BOOK_SORTS` (``popularity`` by default).
    """
    if page < 1:
        raise ValueError("page must be at least 1")
    params = {"page": page, "per_page": AUTHOR_BOOKS_PAGE_SIZE}
    if sort:
        if sort not in AUTHOR_BOOK_SORTS:
            choices = ", ".join(AUTHOR_BOOK_SORTS)
            raise ValueError(f"unknown sort {sort!r}; choose one of: {choices}")
        params["sort"] = AUTHOR_BOOK_SORTS[sort]
    return f"{BASE_URL}/author/list/{author_id(value)}?{urlencode(params)}"


def shelf_slug(value: str) -> str:
    """Normalise a shelf / genre name to its Goodreads slug (``Science Fiction`` ->
    ``science-fiction``). Shelf URLs are accepted too."""
    text = str(value).strip()
    match = re.search(r"/(?:shelf/show|genres)/([^/?#]+)", text)
    if match:
        text = match.group(1)
    slug = "-".join(text.lower().split())
    if not _SHELF_SLUG.match(slug):
        raise ValueError(f"not a Goodreads shelf name: {value!r}")
    return slug


def shelf_url(value: str) -> str:
    """The URL of a shelf (genre tag) page: the most-shelved books for that tag."""
    return f"{BASE_URL}/shelf/show/{shelf_slug(value)}"


def absolute(href: str | None) -> str | None:
    """Make a Goodreads link absolute."""
    if not href:
        return None
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return BASE_URL + href
    return href


__all__ = [
    "AUTHOR_BOOKS_PAGE_SIZE",
    "AUTHOR_BOOK_SORTS",
    "BASE_URL",
    "LIST_PAGE_SIZE",
    "SEARCH_PAGE_SIZE",
    "absolute",
    "author_books_url",
    "author_id",
    "author_url",
    "book_id",
    "book_url",
    "list_id",
    "list_url",
    "reviews_url",
    "search_url",
    "shelf_slug",
    "shelf_url",
]
