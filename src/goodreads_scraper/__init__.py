"""Scrape Goodreads books, reviews, lists, authors and shelves with the ScrapeUnblocker API.

Goodreads closed its public API to new developers in 2020; this package reads the
public pages instead and returns typed records:

* book search results - book and work IDs, title, series, author with follower
  count, average rating, ratings and text-review counts, editions, publication
  date, description, cover and Kindle price;
* book pages - ISBN / ISBN-13 / ASIN, format, pages, publisher, language, edition
  and original publication dates, genres, awards, characters, places, the 1-5 star
  histogram, currently-reading / want-to-read counts and the first 30 reviews;
* reviews - sorted by popularity, newest or oldest, filtered by language,
  edition, star rating or text, page by page;
* Listopia lists (rank, score, votes), author profiles, an author's full book
  list, and the most-shelved books for any genre shelf.

Pages are fetched through the ScrapeUnblocker ``getPageSource`` API; review
sorting, filtering and paging run as browser ``steps`` in the same call.

    >>> from goodreads_scraper import GoodreadsScraper
    >>> goodreads = GoodreadsScraper()                    # reads SCRAPEUNBLOCKER_KEY
    >>> books = goodreads.search("dune", pages=2)
    >>> books[0].title, books[0].author, books[0].average_rating, books[0].ratings_count
    >>> dune = goodreads.book(books[0])
    >>> dune.isbn13, dune.genres, dune.rating_histogram, dune.awards
    >>> goodreads.reviews(dune, sort="newest", language="en", rating=1, pages=2)
"""

from .export import csv_string, flatten, to_json, to_jsonl, write_csv, write_json
from .models import (
    Author,
    AuthorBooksPage,
    Award,
    Book,
    BookDetails,
    BookRow,
    Contributor,
    ListPage,
    Review,
    ReviewPage,
    SearchPage,
    SeriesRef,
    ShelfPage,
)
from .parsing import (
    GoodreadsError,
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
from .scraper import GoodreadsScraper
from .steps import MAX_STEPS, REVIEW_EDITIONS, REVIEW_SORTS, max_review_page, review_steps
from .urls import (
    AUTHOR_BOOK_SORTS,
    author_books_url,
    author_id,
    author_url,
    book_id,
    book_url,
    list_id,
    list_url,
    reviews_url,
    search_url,
    shelf_url,
)

__version__ = "0.1.0"

__all__ = [
    "AUTHOR_BOOK_SORTS",
    "MAX_STEPS",
    "REVIEW_EDITIONS",
    "REVIEW_SORTS",
    "Author",
    "AuthorBooksPage",
    "Award",
    "Book",
    "BookDetails",
    "BookRow",
    "Contributor",
    "GoodreadsError",
    "GoodreadsNotFoundError",
    "GoodreadsParseError",
    "GoodreadsScraper",
    "ListPage",
    "Review",
    "ReviewPage",
    "SearchPage",
    "SeriesRef",
    "ShelfPage",
    "__version__",
    "author_books_url",
    "author_id",
    "author_url",
    "book_id",
    "book_url",
    "csv_string",
    "flatten",
    "list_id",
    "list_url",
    "max_review_page",
    "parse_author_books_page",
    "parse_author_page",
    "parse_book_page",
    "parse_list_page",
    "parse_reviews_page",
    "parse_search_page",
    "parse_shelf_page",
    "review_steps",
    "reviews_url",
    "search_url",
    "shelf_url",
    "to_json",
    "to_jsonl",
    "write_csv",
    "write_json",
]
