"""Command-line interface: ``goodreads-scraper <command> ...``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable, TextIO

from . import __version__
from .export import csv_string, to_json, to_jsonl
from .models import AuthorBooksPage, ListPage, ReviewPage, SearchPage
from .parsing import GoodreadsError
from .scraper import GoodreadsScraper
from .steps import REVIEW_EDITIONS, REVIEW_SORTS, max_review_page
from .urls import AUTHOR_BOOK_SORTS

FORMATS_OUT = ("json", "jsonl", "csv")


def _stdout() -> TextIO:
    """stdout that always accepts UTF-8 (Windows consoles default to a legacy codepage)."""
    stream = sys.stdout
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # pragma: no cover - exotic streams
            pass
    return stream


def _log(args: argparse.Namespace, message: str) -> None:
    if not getattr(args, "quiet", False):
        print(message, file=sys.stderr, flush=True)


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--country",
        metavar="CODE",
        help="Country to route requests through (us, gb, ...); by default "
        "ScrapeUnblocker picks the route",
    )
    parser.add_argument("--retries", type=int, default=3, help="Retries per request (default 3)")
    parser.add_argument("-q", "--quiet", action="store_true", help="No progress on stderr")
    parser.add_argument(
        "-f",
        "--format",
        choices=FORMATS_OUT,
        help="Output format (default: from the --output extension, else json)",
    )
    parser.add_argument("-o", "--output", help="Write to this file instead of stdout")
    parser.add_argument("--pretty", action="store_true", help="Indent JSON output")


def _add_paging(parser: argparse.ArgumentParser, size: int) -> None:
    parser.add_argument(
        "--pages", type=_positive, default=1, help=f"Pages to fetch ({size} per page, default 1)"
    )
    parser.add_argument("--limit", type=_positive, help="Stop after this many records")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goodreads-scraper",
        description="Scrape Goodreads books, reviews, lists, authors and shelves via "
        "ScrapeUnblocker.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Search books by title, author, ISBN or keywords")
    search.add_argument("queries", nargs="+", metavar="QUERY", help="One or more search queries")
    _add_paging(search, 20)
    search.add_argument("--min-rating", type=float, metavar="STARS", help="Lowest average rating")
    search.add_argument("--min-ratings", type=int, metavar="N", help="Fewest number of ratings")
    search.add_argument(
        "--one-per-work",
        action="store_true",
        help="Keep only the first edition found of each work",
    )
    search.add_argument(
        "--details",
        action="store_true",
        help="Also open every book page (ISBNs, genres, awards, ...; one request per book)",
    )
    _add_common(search)

    book = sub.add_parser("book", help="Full details of one or more books")
    book.add_argument("books", nargs="+", metavar="BOOK", help="Book IDs or URLs")
    book.add_argument(
        "--no-reviews",
        action="store_true",
        help="Leave out the first 30 reviews (always left out of CSV)",
    )
    _add_common(book)

    reviews = sub.add_parser("reviews", help="A book's community reviews, sorted and filtered")
    reviews.add_argument("book", metavar="BOOK", help="Book ID or URL")
    reviews.add_argument("--sort", choices=list(REVIEW_SORTS), default="popular")
    reviews.add_argument(
        "--language", metavar="CODE", help="Only reviews in this language (en, es, de, ...)"
    )
    reviews.add_argument(
        "--edition", choices=REVIEW_EDITIONS, default="all", help="all editions (default) or this"
    )
    reviews.add_argument(
        "--rating", type=int, choices=range(1, 6), metavar="STARS", help="Only N-star reviews"
    )
    reviews.add_argument("--search", metavar="TEXT", help="Only reviews mentioning this text")
    reviews.add_argument("--start-page", type=_positive, default=1, help="First page (default 1)")
    _add_paging(reviews, 30)
    _add_common(reviews)

    listopia = sub.add_parser("list", help="Books of a Listopia list with rank, score and votes")
    listopia.add_argument("list", metavar="LIST", help="List ID, slug (1.Best_Books_Ever) or URL")
    _add_paging(listopia, 100)
    _add_common(listopia)

    author = sub.add_parser("author", help="Author profiles with their most popular books")
    author.add_argument("authors", nargs="+", metavar="AUTHOR", help="Author IDs or URLs")
    _add_common(author)

    author_books = sub.add_parser("author-books", help="Every book by an author")
    author_books.add_argument("author", metavar="AUTHOR", help="Author ID or URL")
    author_books.add_argument(
        "--sort", choices=list(AUTHOR_BOOK_SORTS), help="Order (default popularity)"
    )
    _add_paging(author_books, 30)
    _add_common(author_books)

    shelf = sub.add_parser("shelf", help="The most-shelved books for genre / shelf tags")
    shelf.add_argument("shelves", nargs="+", metavar="SHELF", help="e.g. fantasy science-fiction")
    shelf.add_argument("--limit", type=_positive, help="Books per shelf")
    _add_common(shelf)
    return parser


def _format(args: argparse.Namespace) -> str:
    if args.format:
        return args.format
    suffix = Path(args.output).suffix.lower() if args.output else ""
    return {".csv": "csv", ".jsonl": "jsonl", ".ndjson": "jsonl"}.get(suffix, "json")


def _render(records: list[Any], args: argparse.Namespace, drop: Sequence[str] = ()) -> str:
    fmt = _format(args)
    if fmt == "jsonl":
        return to_jsonl(records)
    if fmt == "csv":
        return csv_string(records, drop=drop)
    return to_json(records, pretty=args.pretty) + "\n"


def _emit(records: list[Any], args: argparse.Namespace, drop: Sequence[str] = ()) -> None:
    text = _render(records, args, drop)
    if args.output:
        encoding = "utf-8-sig" if _format(args) == "csv" else "utf-8"
        with open(Path(args.output), "w", encoding=encoding, newline="") as handle:
            handle.write(text)
        _log(args, f"wrote {len(records)} record(s) to {args.output}")
    else:
        _stdout().write(text)


def _scraper(args: argparse.Namespace) -> GoodreadsScraper:
    def on_retry(attempt: int, delay: float, error: BaseException) -> None:
        _log(args, f"  retry {attempt} in {delay:.0f}s ({type(error).__name__}: {error})")

    return GoodreadsScraper(country=args.country, retries=args.retries, on_retry=on_retry)


def _on_error(args: argparse.Namespace, failures: list[str]) -> Callable[[str, Exception], None]:
    def handler(item: str, exc: Exception) -> None:
        failures.append(item)
        _log(args, f"  skipped {item}: {type(exc).__name__}: {exc}")

    return handler


def _cmd_search(args: argparse.Namespace, scraper: GoodreadsScraper | None) -> int:
    scraper = scraper or _scraper(args)

    def on_page(page: SearchPage) -> None:
        total = f" of about {page.total_results:,}" if page.total_results else ""
        _log(args, f"  page {page.page}: {len(page.books)} books{total}")

    def on_query(query: str, found: list[Any]) -> None:
        _log(args, f"  {len(found)} book(s) for {query!r}")

    books = scraper.search_many(
        args.queries,
        pages=args.pages,
        limit=args.limit,
        min_rating=args.min_rating,
        min_ratings=args.min_ratings,
        one_per_work=args.one_per_work,
        on_page=on_page,
        on_query=on_query,
    )
    if not args.details:
        _emit(books, args)
        return 0
    failures: list[str] = []
    details = scraper.books(books, on_error=_on_error(args, failures))
    _emit(details, args, drop=("reviews",))
    return 1 if failures and not details else 0


def _cmd_book(args: argparse.Namespace, scraper: GoodreadsScraper | None) -> int:
    scraper = scraper or _scraper(args)
    failures: list[str] = []
    details = scraper.books(args.books, on_error=_on_error(args, failures))
    if args.no_reviews:
        for item in details:
            item.reviews = []
    _emit(details, args, drop=("reviews",))
    return 1 if failures and not details else 0


def _cmd_reviews(args: argparse.Namespace, scraper: GoodreadsScraper | None) -> int:
    filters = {
        "sort": args.sort,
        "language": args.language,
        "edition": args.edition,
        "rating": args.rating,
        "search": args.search,
    }
    deepest = max_review_page(**filters)
    if args.start_page > deepest:
        raise ValueError(
            f"with these filters one request reaches review page {deepest} at most "
            f"(--start-page {args.start_page})"
        )
    if args.start_page + args.pages - 1 > deepest:
        _log(args, f"note: with these filters one request reaches review page {deepest} at most")
    scraper = scraper or _scraper(args)

    def on_page(page: ReviewPage) -> None:
        span = f" ({page.first}-{page.last} of {page.total:,})" if page.first else ""
        applied = f" [{', '.join(page.applied_filters)}]" if page.applied_filters else ""
        _log(args, f"  page {page.page}: {len(page.reviews)} reviews{span}{applied}")

    found = scraper.reviews(
        args.book,
        pages=args.pages,
        start_page=args.start_page,
        limit=args.limit,
        on_page=on_page,
        **filters,
    )
    _emit(found, args)
    return 0


def _cmd_list(args: argparse.Namespace, scraper: GoodreadsScraper | None) -> int:
    scraper = scraper or _scraper(args)

    def on_page(page: ListPage) -> None:
        if page.page == 1:
            size = f" - {page.books_count:,} books" if page.books_count else ""
            voters = f", {page.voters_count:,} voters" if page.voters_count else ""
            _log(args, f"{page.title or page.url}{size}{voters}")
        _log(args, f"  page {page.page}: {len(page.books)} books")

    books = scraper.listopia(args.list, pages=args.pages, limit=args.limit, on_page=on_page)
    _emit(books, args)
    return 0


def _cmd_author(args: argparse.Namespace, scraper: GoodreadsScraper | None) -> int:
    scraper = scraper or _scraper(args)
    failures: list[str] = []
    found = []
    for item in args.authors:
        try:
            found.append(scraper.author(item))
        except GoodreadsError as exc:
            _on_error(args, failures)(item, exc)
    _emit(found, args)
    return 1 if failures and not found else 0


def _cmd_author_books(args: argparse.Namespace, scraper: GoodreadsScraper | None) -> int:
    scraper = scraper or _scraper(args)

    def on_page(page: AuthorBooksPage) -> None:
        of = f" of {page.last_page}" if page.last_page else ""
        _log(args, f"  page {page.page}{of}: {len(page.books)} books by {page.author}")

    books = scraper.author_books(
        args.author, pages=args.pages, sort=args.sort, limit=args.limit, on_page=on_page
    )
    _emit(books, args)
    return 0


def _cmd_shelf(args: argparse.Namespace, scraper: GoodreadsScraper | None) -> int:
    scraper = scraper or _scraper(args)
    failures: list[str] = []
    books = []
    for name in args.shelves:
        try:
            page = scraper.shelf(name)
        except GoodreadsError as exc:
            _on_error(args, failures)(name, exc)
            continue
        _log(args, f"  {page.title or page.shelf}: {len(page.books)} books")
        books.extend(page.books[: args.limit] if args.limit else page.books)
    _emit(books, args)
    return 1 if failures and not books else 0


COMMANDS = {
    "search": _cmd_search,
    "book": _cmd_book,
    "reviews": _cmd_reviews,
    "list": _cmd_list,
    "author": _cmd_author,
    "author-books": _cmd_author_books,
    "shelf": _cmd_shelf,
}


def main(argv: Sequence[str] | None = None, *, scraper: GoodreadsScraper | None = None) -> int:
    """Run the CLI. ``scraper`` lets tests inject a scraper with a mocked client."""
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args, scraper)
    except (GoodreadsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        if not type(exc).__module__.startswith("scrapeunblocker"):
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)  # API errors, e.g. a bad key
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
