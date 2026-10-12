"""Typed records returned by the scraper. Every record has ``to_dict()``.

Dates are ISO strings (``2019-10-01``); IDs are Goodreads' numeric IDs, the ones
in its URLs (``/book/show/44767458``, ``/author/show/58``, ``/work/editions/3634639``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _plain(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


class _Record:
    def to_dict(self) -> dict[str, Any]:
        return {key: _plain(value) for key, value in asdict(self).items()}  # type: ignore[call-overload]


@dataclass
class Contributor(_Record):
    """An author, editor, translator, illustrator, ... of a book."""

    name: str
    role: str | None = None
    author_id: int | None = None
    url: str | None = None
    followers: int | None = None
    works_count: int | None = None
    goodreads_author: bool | None = None
    image: str | None = None


@dataclass
class SeriesRef(_Record):
    """A series a book belongs to, with the book's place in it (``1``, ``0.5``, ``1-3``)."""

    title: str
    position: str | None = None
    url: str | None = None


@dataclass
class Award(_Record):
    """A literary award the work won or was nominated for."""

    name: str
    category: str | None = None
    designation: str | None = None
    year: int | None = None
    url: str | None = None


@dataclass
class Book(_Record):
    """One book of the Goodreads search results.

    ``average_rating``, ``ratings_count``, ``reviews_count`` and ``editions_count``
    cover the whole work (every edition), as Goodreads shows them.
    ``publication_date`` is this edition's.
    """

    book_id: int
    title: str
    url: str
    author: str | None = None
    author_id: int | None = None
    author_url: str | None = None
    author_followers: int | None = None
    author_works: int | None = None
    contributors: list[Contributor] = field(default_factory=list)
    series: list[SeriesRef] = field(default_factory=list)
    work_id: int | None = None
    average_rating: float | None = None
    ratings_count: int | None = None
    reviews_count: int | None = None
    editions_count: int | None = None
    publication_date: str | None = None
    description: str | None = None
    cover: str | None = None
    kindle_price: float | None = None
    position: int | None = None
    page: int | None = None
    query: str | None = None


@dataclass
class SearchPage(_Record):
    """One page (20 books) of search results.

    ``total_results`` is Goodreads' own rounded count ("over 108k" -> 108000).
    """

    query: str
    page: int
    url: str
    books: list[Book] = field(default_factory=list)
    total_results: int | None = None
    has_next: bool = False


@dataclass
class Review(_Record):
    """One community review.

    ``rating`` is the reviewer's star rating (quarter stars are possible, e.g.
    ``1.25``); ``None`` when they did not rate. Reviewer follower counts are
    rounded the way Goodreads shows them ("29.1k").
    """

    review_id: int | None
    url: str | None
    rating: float | None = None
    date: str | None = None
    text: str = ""
    has_spoilers: bool = False
    shelves: list[str] = field(default_factory=list)
    likes: int = 0
    comments: int = 0
    reviewer: str | None = None
    reviewer_id: int | None = None
    reviewer_url: str | None = None
    reviewer_is_author: bool = False
    reviewer_reviews: int | None = None
    reviewer_books: int | None = None
    reviewer_followers: int | None = None
    book_id: int | None = None
    position: int | None = None
    page: int | None = None


@dataclass
class ReviewPage(_Record):
    """One page (30) of a book's reviews, with the filters Goodreads says are applied."""

    book_id: int
    page: int
    url: str
    reviews: list[Review] = field(default_factory=list)
    total: int | None = None
    first: int | None = None
    last: int | None = None
    applied_filters: list[str] = field(default_factory=list)
    has_next: bool = False


@dataclass
class BookDetails(_Record):
    """Everything on a book page.

    Ratings, reviews, awards, characters and places are for the work (every
    edition); ISBNs, format, pages, publisher, language and ``publication_date``
    belong to this edition. ``rating_histogram`` maps ``"1"``..``"5"`` stars to
    the number of ratings. ``reviews`` holds the first page (30) of community
    reviews.
    """

    book_id: int
    title: str
    url: str
    title_complete: str | None = None
    original_title: str | None = None
    work_id: int | None = None
    authors: list[Contributor] = field(default_factory=list)
    series: list[SeriesRef] = field(default_factory=list)
    description: str | None = None
    genres: list[str] = field(default_factory=list)
    average_rating: float | None = None
    ratings_count: int | None = None
    reviews_count: int | None = None
    rating_histogram: dict[str, int] = field(default_factory=dict)
    currently_reading: int | None = None
    want_to_read: int | None = None
    format: str | None = None
    pages: int | None = None
    publisher: str | None = None
    language: str | None = None
    isbn: str | None = None
    isbn13: str | None = None
    asin: str | None = None
    publication_date: str | None = None
    original_publication_date: str | None = None
    awards: list[Award] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    quotes_count: int | None = None
    questions_count: int | None = None
    discussions_count: int | None = None
    review_languages: dict[str, int] = field(default_factory=dict)
    kindle_price: float | None = None
    cover: str | None = None
    editions_url: str | None = None
    reviews: list[Review] = field(default_factory=list)


@dataclass
class BookRow(_Record):
    """A book as listed on a Listopia list, an author's book list or a shelf page.

    ``title`` has the series suffix removed; it is in ``series`` and
    ``series_position`` (``"The Hunger Games (The Hunger Games, #1)"`` ->
    ``"The Hunger Games"``, ``"The Hunger Games"``, ``"1"``). ``rank``, ``score``
    and ``votes`` are filled on Listopia lists, ``shelved_count`` on shelf pages.
    ``source`` says where the row came from: ``list:1``, ``author:58``,
    ``shelf:fantasy``.
    """

    book_id: int
    title: str
    url: str
    author: str | None = None
    author_id: int | None = None
    author_url: str | None = None
    contributors: list[Contributor] = field(default_factory=list)
    series: str | None = None
    series_position: str | None = None
    average_rating: float | None = None
    ratings_count: int | None = None
    published_year: int | None = None
    editions_count: int | None = None
    rank: int | None = None
    score: int | None = None
    votes: int | None = None
    shelved_count: int | None = None
    cover: str | None = None
    source: str | None = None


@dataclass
class ListPage(_Record):
    """One page (100 books) of a Listopia list."""

    list_id: int
    page: int
    url: str
    title: str | None = None
    description: str | None = None
    books_count: int | None = None
    voters_count: int | None = None
    created: str | None = None
    created_by: str | None = None
    tags: list[str] = field(default_factory=list)
    books: list[BookRow] = field(default_factory=list)
    last_page: int | None = None
    has_next: bool = False


@dataclass
class Author(_Record):
    """An author profile. ``top_books`` are the author's most popular books as the
    profile shows them; :meth:`GoodreadsScraper.author_books` pages through all."""

    author_id: int
    name: str
    url: str
    image: str | None = None
    born: str | None = None
    birthplace: str | None = None
    died: str | None = None
    website: str | None = None
    twitter: str | None = None
    genres: list[str] = field(default_factory=list)
    influences: list[str] = field(default_factory=list)
    member_since: str | None = None
    about: str | None = None
    average_rating: float | None = None
    ratings_count: int | None = None
    reviews_count: int | None = None
    works_count: int | None = None
    top_books: list[BookRow] = field(default_factory=list)


@dataclass
class AuthorBooksPage(_Record):
    """One page (30 books) of an author's full book list."""

    author_id: int
    page: int
    url: str
    author: str | None = None
    sort: str | None = None
    books: list[BookRow] = field(default_factory=list)
    last_page: int | None = None
    has_next: bool = False


@dataclass
class ShelfPage(_Record):
    """The most-shelved books for a shelf / genre tag (Goodreads shows 50 signed out)."""

    shelf: str
    url: str
    title: str | None = None
    books: list[BookRow] = field(default_factory=list)


__all__ = [
    "Author",
    "AuthorBooksPage",
    "Award",
    "Book",
    "BookDetails",
    "BookRow",
    "Contributor",
    "ListPage",
    "Review",
    "ReviewPage",
    "SearchPage",
    "SeriesRef",
    "ShelfPage",
]
