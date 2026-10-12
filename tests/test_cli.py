from __future__ import annotations

import csv
import json

import pytest

from goodreads_scraper.cli import build_parser, main

from .conftest import (
    author_books_html,
    author_html,
    book_html,
    list_html,
    reviews_html,
    search_html,
    sequence,
    shelf_html,
)


def test_parser_search_defaults():
    args = build_parser().parse_args(["search", "dune", "foundation"])
    assert args.queries == ["dune", "foundation"]
    assert args.pages == 1 and args.limit is None
    assert args.format is None and args.output is None
    assert not args.details and not args.one_per_work


def test_parser_reviews_options():
    args = build_parser().parse_args(
        [
            "reviews",
            "44767458",
            "--sort",
            "newest",
            "--language",
            "en",
            "--rating",
            "1",
            "--search",
            "spice",
            "--pages",
            "2",
            "--edition",
            "this",
        ]
    )
    assert (args.sort, args.language, args.rating, args.search) == ("newest", "en", 1, "spice")
    assert args.pages == 2 and args.edition == "this" and args.start_page == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["reviews", "1", "--rating", "6"],
        ["reviews", "1", "--sort", "best"],
        ["search", "dune", "--pages", "0"],
        ["author-books", "58", "--sort", "newest"],
        ["shelf"],
    ],
)
def test_parser_rejects_bad_input(argv):
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


def test_search_to_json_stdout(make_scraper, capsys):
    scraper, _ = make_scraper(sequence(search_html()))
    assert main(["search", "dune", "--limit", "2", "-q"], scraper=scraper) == 0
    data = json.loads(capsys.readouterr().out)
    assert [b["title"] for b in data] == ["Dune", "Dune Messiah"]


def test_search_with_details_to_csv(make_scraper, tmp_path):
    def handler(url, options):
        return book_html() if "/book/show/" in url else search_html()

    scraper, client = make_scraper(handler)
    out = tmp_path / "books.csv"
    code = main(
        ["search", "dune", "--limit", "1", "--details", "-o", str(out), "-q"], scraper=scraper
    )
    assert code == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert rows[0]["isbn13"] == "9780593099322"
    assert rows[0]["authors"] == "Frank Herbert | Brian Herbert (Introduction)"
    assert rows[0]["rating_histogram"].startswith("1: 26182 | 2: 56084")
    assert "reviews" not in rows[0]


def test_book_json_without_reviews(make_scraper, tmp_path):
    scraper, _ = make_scraper(sequence(book_html()))
    out = tmp_path / "book.json"
    assert main(["book", "44767458", "--no-reviews", "-o", str(out), "-q"], scraper=scraper) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["title"] == "Dune" and data[0]["reviews"] == []


def test_reviews_to_jsonl(make_scraper, tmp_path):
    scraper, client = make_scraper(sequence(reviews_html(first=31)))
    out = tmp_path / "reviews.jsonl"
    code = main(["reviews", "1", "--start-page", "2", "-o", str(out), "-q"], scraper=scraper)
    assert code == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 30 and json.loads(lines[0])["position"] == 31


def test_reviews_page_out_of_reach_is_an_error(make_scraper, capsys):
    scraper, client = make_scraper(sequence(reviews_html()))
    code = main(["reviews", "1", "--sort", "newest", "--start-page", "7"], scraper=scraper)
    assert code == 2
    assert "page 6 at most" in capsys.readouterr().err
    assert client.calls == []


def test_list_author_books_and_shelf(make_scraper, capsys):
    def handler(url, options):
        if "/list/show/" in url:
            return list_html(last_page=1)
        if "/author/list/" in url:
            return author_books_html(last_page=1)
        if "/author/show/" in url:
            return author_html()
        return shelf_html()

    scraper, _ = make_scraper(handler)
    assert main(["list", "1", "-q"], scraper=scraper) == 0
    assert [b["rank"] for b in json.loads(capsys.readouterr().out)] == [1, 2]
    assert main(["author", "58", "-q"], scraper=scraper) == 0
    assert json.loads(capsys.readouterr().out)[0]["born"] == "1920-10-08"
    assert main(["author-books", "58", "--sort", "published", "-q"], scraper=scraper) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
    assert main(["shelf", "science-fiction", "-q", "-f", "csv"], scraper=scraper) == 0
    rows = list(csv.DictReader(capsys.readouterr().out.splitlines()))
    assert rows[0]["shelved_count"] == "22035"


def test_missing_book_exits_with_failure(make_scraper, capsys):
    from .conftest import TargetNotFoundError

    scraper, _ = make_scraper(sequence(TargetNotFoundError("404")))
    assert main(["book", "1"], scraper=scraper) == 1
    assert "skipped 1" in capsys.readouterr().err
